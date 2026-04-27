from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model
from core.tenancy import SchoolScopedModel

User = get_user_model()


class AIChatSession(models.Model):
    """A chat session with the AI assistant."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_chat_sessions')
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ai_chat_sessions',
        help_text="School context — ensures sessions are tenant-scoped.",
    )
    session_id = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=255, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    total_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Cumulative tokens used in this session (input + output).",
    )

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['school', 'user'], name='idx_aichat_school_user'),
        ]

    def __str__(self):
        return f"{self.user} - {self.title}"

    def add_tokens(self, count: int) -> None:
        """Atomically increment total_tokens on session and on monthly school counter."""
        n = max(0, int(count))
        if n == 0:
            return
        AIChatSession.objects.filter(pk=self.pk).update(
            total_tokens=models.F('total_tokens') + n
        )
        self.total_tokens += n
        if self.school_id:
            from django.utils import timezone
            now = timezone.now()
            SchoolMonthlyTokenUsage.increment(self.school_id, now.year, now.month, n)

    @classmethod
    def monthly_usage_for_school(cls, school, year: int, month: int) -> int:
        """Total tokens consumed for a school in a given calendar month.

        Counts ConversationHistory.token_count where the *message* was created
        in that month — not the session — so long-lived sessions are bucketed
        correctly across month boundaries.
        """
        from django.db.models import Sum
        result = (
            ConversationHistory.objects.filter(
                session__school=school,
                created_at__year=year,
                created_at__month=month,
            ).aggregate(total=Sum("token_count"))["total"]
        )
        return result or 0

    @classmethod
    def check_school_token_cap(cls, school, extra: int = 0) -> tuple[bool, int, int]:
        """Check whether a school has capacity for ``extra`` more tokens this month.

        Returns (allowed, used, cap).
        Uses SchoolMonthlyTokenUsage for O(1) lookup; falls back to aggregation.
        Cap is read from school.ai_monthly_token_cap; 0 means unlimited.
        """
        from django.utils import timezone
        now = timezone.now()
        cap = getattr(school, "ai_monthly_token_cap", 0) or 0
        if cap == 0:
            return True, 0, 0
        used = SchoolMonthlyTokenUsage.get_usage(school.pk, now.year, now.month)
        if used == 0:
            used = cls.monthly_usage_for_school(school, now.year, now.month)
        allowed = (used + extra) <= cap
        return allowed, used, cap


class ConversationHistory(models.Model):
    """Conversation history for the AI chatbot."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]

    session = models.ForeignKey(AIChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    token_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class PromptTemplate(SchoolScopedModel):
    """Predefined prompt templates for the AI assistant.

    Templates with ``school=None`` are global defaults visible to all schools.
    Templates with a specific school FK override the global default for that
    tenant, enabling per-school AI customisation (curriculum context, tone, etc.).
    """
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='prompt_templates',
        help_text="Leave blank for a global template. Set to override for a specific school.",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    system_prompt = models.TextField(help_text="System prompt for the AI")
    user_prompt_template = models.TextField(blank=True, help_text="Template for user input")
    is_active = models.BooleanField(default=True)
    category = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'name'],
                name='uniq_prompttemplate_school_name',
            ),
        ]

    def __str__(self):
        return self.name


class SchoolMonthlyTokenUsage(models.Model):
    """Denormalized monthly token counter per school — O(1) cap enforcement.

    Incremented atomically via ``increment()`` each time tokens are consumed.
    Avoids full-table aggregation on every AI request.
    """

    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='monthly_token_usage',
    )
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    tokens_used = models.PositiveBigIntegerField(default=0)

    class Meta:
        unique_together = [("school", "year", "month")]
        indexes = [
            models.Index(fields=["school", "year", "month"], name="idx_tokusage_school_ym"),
        ]

    def __str__(self):
        return f"{self.school_id} {self.year}-{self.month:02d}: {self.tokens_used}"

    @classmethod
    def increment(cls, school_id: int, year: int, month: int, count: int) -> None:
        """Atomically add ``count`` tokens to the school-month bucket."""
        cls.objects.update_or_create(
            school_id=school_id, year=year, month=month,
            defaults={},
        )
        cls.objects.filter(school_id=school_id, year=year, month=month).update(
            tokens_used=models.F("tokens_used") + count
        )

    @classmethod
    def get_usage(cls, school_id: int, year: int, month: int) -> int:
        row = cls.objects.filter(school_id=school_id, year=year, month=month).values_list("tokens_used", flat=True).first()
        return int(row) if row else 0