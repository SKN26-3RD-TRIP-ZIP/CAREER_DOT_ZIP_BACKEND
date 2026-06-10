"""
Pipeline 3 - ① 사전 적재 (Analysis 단계 아님, 서비스 운영 전 1회성 작업)

역할:
  MySQL question_bank에 저장된 질문 데이터를 전처리하고
  OpenAI 임베딩을 생성해 Pinecone에 저장한다.
  이 작업은 서비스 배포 전 또는 질문 은행 대규모 업데이트 시 1회 실행한다.

  실행 방법:
    python manage.py embed_question_bank
    python manage.py embed_question_bank --batch-size 50 --dry-run

포함 함수:
  preprocess_questions()   질문 텍스트 정제 + 미임베딩 항목 필터링
  embed_and_upsert()       임베딩 생성 + Pinecone upsert
  run_full_pipeline()      전체 사전 적재 파이프라인 실행
"""

import logging
import re

from django.conf import settings
from openai import OpenAI
from pinecone import Pinecone

from apps.question_bank.models import QuestionBankItem

logger = logging.getLogger(__name__)

# 질문 텍스트 앞에 붙는 노이즈 패턴 (예: "Q.", "질문:", "1.", "문1.")
_NOISE_RE = re.compile(r'^(?:Q\.|질문\s*[:：]|문\s*\d+\s*[.)】]|\d+\s*[.)】])\s*', re.IGNORECASE)


def preprocess_questions(limit: int = 0) -> list[dict]:
    """
    MySQL question_bank에서 is_embedded=False인 활성 항목을 불러와 전처리한다.

    반환 형식:
    [
        {
            "id":            "uuid 문자열",
            "question_text": "정제된 질문 텍스트",
            "question_type": "technical" | "personality" | "job",
            "keywords":      ["Redis", "캐싱"],
            "source":        "aihub",
        },
        ...
    ]
    """
    qs = (
        QuestionBankItem.objects
        .filter(is_active=True, is_embedded=False)
        .only("id", "question_text", "question_type", "keywords", "source")
    )
    if limit:
        qs = qs[:limit]

    result = []
    for item in qs:
        text = item.question_text.strip()
        text = re.sub(r'\s+', ' ', text)
        text = _NOISE_RE.sub('', text).strip()
        if not text:
            continue
        result.append({
            "id":            str(item.id),
            "question_text": text,
            "question_type": item.question_type,
            "keywords":      item.keywords or [],
            "source":        item.source,
        })

    logger.info("preprocess_questions: %d개 항목 전처리 완료", len(result))
    return result


def embed_and_upsert(
    questions: list[dict],
    pinecone_index_name: str,
    batch_size: int = 100,
    dry_run: bool = False,
) -> dict:
    """
    전처리된 질문 목록을 임베딩하고 Pinecone에 upsert한다.

    반환 형식:
    {
        "total":    1000,
        "upserted": 950,
        "skipped":  50,
        "failed":   0,
    }
    """
    stats = {"total": len(questions), "upserted": 0, "skipped": 0, "failed": 0}

    if not questions:
        return stats

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    if not dry_run:
        pc    = Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index(pinecone_index_name)

    for batch_start in range(0, len(questions), batch_size):
        batch = questions[batch_start: batch_start + batch_size]
        texts = [q["question_text"] for q in batch]

        try:
            response   = client.embeddings.create(model="text-embedding-3-small", input=texts)
            embeddings = [item.embedding for item in response.data]
        except Exception as e:
            logger.error("임베딩 생성 실패 (batch %d~%d): %s", batch_start, batch_start + len(batch), e)
            stats["failed"] += len(batch)
            continue

        vectors = [
            {
                "id":     q["id"],
                "values": emb,
                "metadata": {
                    "question_id":   q["id"],
                    "question_text": q["question_text"],
                    "type":          q["question_type"],
                    "source":        "question_bank",
                    "keywords":      q["keywords"],
                },
            }
            for q, emb in zip(batch, embeddings)
        ]

        if dry_run:
            logger.info("[dry-run] upsert 대상 %d개 (실제 저장 안 함)", len(vectors))
            stats["upserted"] += len(vectors)
            continue

        try:
            index.upsert(vectors=vectors)
        except Exception as e:
            logger.error("Pinecone upsert 실패 (batch %d~%d): %s", batch_start, batch_start + len(batch), e)
            stats["failed"] += len(batch)
            continue

        # is_embedded=True 업데이트
        ids = [q["id"] for q in batch]
        QuestionBankItem.objects.filter(id__in=ids).update(is_embedded=True)
        stats["upserted"] += len(batch)

        logger.info(
            "진행 중: %d / %d (누적 upserted=%d, failed=%d)",
            batch_start + len(batch), len(questions), stats["upserted"], stats["failed"],
        )

    return stats


def run_full_pipeline(
    pinecone_index_name: str | None = None,
    batch_size: int = 100,
    dry_run: bool = False,
) -> dict:
    """
    전체 사전 적재 파이프라인을 순서대로 실행한다.
    management command(embed_question_bank)에서 이 함수를 호출한다.

    실행 순서:
      1. preprocess_questions() — 정제 및 미임베딩 항목 필터링
      2. embed_and_upsert()     — 임베딩 생성 + Pinecone 저장

    dry_run=True 시:
      실제 Pinecone upsert 없이 전처리 결과만 확인
    """
    index_name = pinecone_index_name or settings.PINECONE_INDEX_NAME
    if not index_name:
        raise ValueError("PINECONE_INDEX_NAME이 설정되지 않았습니다.")

    logger.info("=== Pinecone 사전 적재 시작 (dry_run=%s) ===", dry_run)

    questions = preprocess_questions()
    if not questions:
        logger.info("적재할 항목이 없습니다. (모두 is_embedded=True)")
        return {"total": 0, "upserted": 0, "skipped": 0, "failed": 0}

    stats = embed_and_upsert(
        questions=questions,
        pinecone_index_name=index_name,
        batch_size=batch_size,
        dry_run=dry_run,
    )

    logger.info(
        "=== 사전 적재 완료 === total=%d upserted=%d skipped=%d failed=%d",
        stats["total"], stats["upserted"], stats["skipped"], stats["failed"],
    )
    return stats
