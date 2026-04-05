from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class AIChatSession(models.Model):
    """A chat session with the AI assistant."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_chat_sessions')
    session_id = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=255, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user} - {self.title}"


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


class PromptTemplate(models.Model):
    """Predefined prompt templates for the AI assistant."""
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    system_prompt = models.TextField(help_text="System prompt for the AI")
    user_prompt_template = models.TextField(blank=True, help_text="Template for user input")
    is_active = models.BooleanField(default=True)
    category = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name