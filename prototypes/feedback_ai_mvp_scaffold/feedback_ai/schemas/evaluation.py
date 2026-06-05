from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

# Input Schema (From QuestionOutput_schema.md)
class WeaknessTagTrigger(BaseModel):
    weakness_tag_id: str
    tag_name: str
    reason: str
    priority_rank: int
    is_selected_for_followup: bool

class SelectedWeaknessTag(BaseModel):
    weakness_tag_id: str
    tag_name: str
    reason: str

class AnswerSufficiencyInput(BaseModel):
    answer_id: str
    is_sufficient: bool
    sufficiency_reason: str
    answer_weakness_tags: List[WeaknessTagTrigger]
    selected_weakness_tag: Optional[SelectedWeaknessTag] = None
    should_generate_followup: bool
    next_action: str

# Database / Output Schema (For evaluations / sample_summary.md)
class StarSegment(BaseModel):
    desc: str
    score: float

class BeiLogic(BaseModel):
    regex_filter_passed: bool = True
    raw_word_count: int
    situation: StarSegment
    task: StarSegment
    action: StarSegment
    result: StarSegment

class CbiCompetency(BaseModel):
    assigned_level: int
    evidence_sentence: str

class TechnicalGrounding(BaseModel):
    tech_stack: str
    before_metric: str
    after_metric: str
    is_grounded: bool

class SpeechDelivery(BaseModel):
    filler_word_counts: Dict[str, int]
    total_filler_count: int
    repetition_words: List[str]
    is_sentence_incomplete: bool

class TagLog(BaseModel):
    tag_name: str
    category: str
    description: str
    trigger_signal: str

class PipelineTags(BaseModel):
    strengths: List[TagLog] = []
    weaknesses: List[TagLog] = []

class EvaluationMasterResult(BaseModel):
    evaluation_metadata: Dict[str, str] = {
        "engine_version": "v1.2.0-MVP",
        "calculated_at": datetime.utcnow().isoformat() + "Z",
        "is_fallback_applied": "false"
    }
    score_summary: Dict[str, Any]
    score_detail: Dict[str, Any]
    dynamically_triggered_tags: PipelineTags