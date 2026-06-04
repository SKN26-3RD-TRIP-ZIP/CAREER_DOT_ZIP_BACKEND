import uuid
from django.db import models
from apps.interview.models import InterviewAnswer


class Evaluation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.OneToOneField(InterviewAnswer, on_delete=models.CASCADE, related_name='evaluation')
    bei_score = models.JSONField(default=dict, blank=True)
    cbi_score = models.JSONField(default=dict, blank=True)
    filler_words = models.JSONField(default=dict, blank=True)
    sbert_db_similarity = models.FloatField(blank=True, null=True)
    sbert_readme_similarity = models.FloatField(blank=True, null=True)
    llm_concept_score = models.PositiveIntegerField(blank=True, null=True)
    final_tech_score = models.PositiveIntegerField(blank=True, null=True)
    score_detail = models.JSONField(default=dict, blank=True)
    evaluated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evaluations'
        ordering = ['-evaluated_at']

    def __str__(self):
        return f"Evaluation for answer {self.answer.id}"


class WeaknessTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tag_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'weakness_tags'
        ordering = ['tag_name']

    def __str__(self):
        return self.tag_name


class StrengthTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tag_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'strength_tags'
        ordering = ['tag_name']

    def __str__(self):
        return self.tag_name


class AnswerWeaknessTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.ForeignKey(InterviewAnswer, on_delete=models.CASCADE, related_name='weakness_mappings')
    weakness_tag = models.ForeignKey(WeaknessTag, on_delete=models.CASCADE)
    reason = models.TextField(blank=True, null=True)
    priority_rank = models.PositiveIntegerField(default=1)
    is_selected_for_followup = models.BooleanField(default=False)
    used_for = models.CharField(max_length=50, blank=True, null=True)
    followup_question_id = models.UUIDField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'answer_weakness_tags'
        ordering = ['priority_rank', 'created_at']

    def __str__(self):
        return f"{self.answer.id} - {self.weakness_tag.tag_name}"


class AnswerStrengthTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.ForeignKey(InterviewAnswer, on_delete=models.CASCADE, related_name='strength_mappings')
    strength_tag = models.ForeignKey(StrengthTag, on_delete=models.CASCADE)
    reason = models.TextField(blank=True, null=True)
    priority_rank = models.PositiveIntegerField(default=1)
    trigger_signal_log = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'answer_strength_tags'
        ordering = ['priority_rank', 'created_at']

    def __str__(self):
        return f"{self.answer.id} - {self.strength_tag.tag_name}"
