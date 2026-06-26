"""Assistant core — compile a company profile + retrieved context into a
grounded support answer.

This is the analogue of Aether's L6 persona compiler: a ``company.yaml`` is
compiled into a support-assistant system prompt, RAG context is retrieved from
the company's knowledge base, the LLM (Ollama) is called, and the answer is
returned with citations. If Ollama is down, a clear grounded stub is returned
so the demo never hard-fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from customer_assistant.config import CompanyProfile
from customer_assistant.knowledge_base import KnowledgeBase, RetrievedChunk
from customer_assistant.llm import ChatMessage, OllamaClient, OllamaUnavailable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Citation:
    """A source citation surfaced to the caller/UI."""

    source: str
    snippet: str


@dataclass(slots=True)
class AssistantReply:
    """Structured result of a /chat turn."""

    answer: str
    citations: list[Citation] = field(default_factory=list)
    model: str = ""
    degraded: bool = False  # True when answered without the LLM (Ollama down)
    escalate: bool = False  # True when the message hit an escalation trigger


def build_system_prompt(profile: CompanyProfile, context_chunks: list[RetrievedChunk]) -> str:
    """Compile the company profile + retrieved context into a system prompt."""
    c = profile.company
    parts: list[str] = []

    parts.append(
        f"You are the customer-support assistant for {c.display_name}"
        + (f" ({c.tagline})." if c.tagline else ".")
    )
    parts.append(f"Your tone is {profile.branding.tone}.")

    if profile.support.in_scope:
        parts.append(
            "You help customers with: " + "; ".join(profile.support.in_scope) + "."
        )
    if profile.support.out_of_scope:
        parts.append(
            "You must NOT attempt to handle: "
            + "; ".join(profile.support.out_of_scope)
            + ". For those, politely defer or escalate."
        )

    if profile.escalation.enabled:
        triggers = "; ".join(profile.escalation.triggers) or "anything you cannot resolve"
        contact_bits = []
        ct = profile.escalation.contact
        if ct.email:
            contact_bits.append(f"email {ct.email}")
        if ct.phone:
            contact_bits.append(f"phone {ct.phone}")
        if ct.hours:
            contact_bits.append(f"hours {ct.hours}")
        contact = (" Human support: " + ", ".join(contact_bits) + ".") if contact_bits else ""
        parts.append(
            f"Escalate to a human when the customer raises: {triggers}. "
            f'When escalating, say: "{profile.escalation.message}".{contact}'
        )

    enabled_tools = [t for t in profile.tools if t.enabled]
    if enabled_tools:
        tool_lines = "; ".join(f"{t.name} ({t.description})" for t in enabled_tools)
        parts.append(f"Tools you may use: {tool_lines}.")

    parts.append(
        "Ground every factual claim in the CONTEXT below. If the context does "
        "not contain the answer, say you don't have that information and offer "
        "to escalate — never invent policy details, prices, or dates. Keep "
        "answers short and specific. Cite the source filename in square brackets "
        "after any fact you draw from the context, e.g. [returns-policy.md]."
    )

    if context_chunks:
        parts.append("\n--- CONTEXT ---")
        for ch in context_chunks:
            parts.append(f"[{ch.source}]\n{ch.text}")
        parts.append("--- END CONTEXT ---")
    else:
        parts.append(
            "\n(No relevant knowledge-base context was found for this question.)"
        )

    return "\n\n".join(parts)


def _check_escalation(profile: CompanyProfile, message: str) -> bool:
    """Heuristic: does the user message contain an escalation trigger keyword?"""
    if not profile.escalation.enabled:
        return False
    low = message.lower()
    return any(trigger.lower() in low for trigger in profile.escalation.triggers)


def _stub_answer(profile: CompanyProfile, chunks: list[RetrievedChunk]) -> str:
    """Compose a grounded answer without the LLM (used when Ollama is down)."""
    if not chunks:
        msg = (
            f"I'm the {profile.company.display_name} assistant. I can't reach the "
            "language model right now, and I didn't find anything in our help "
            "articles matching your question."
        )
        if profile.escalation.enabled:
            msg += " " + profile.escalation.message
        return msg
    lead = (
        f"I'm the {profile.company.display_name} assistant. (The language model "
        "is offline, so here's the most relevant information from our help "
        "center.)\n"
    )
    body = "\n\n".join(f"From [{ch.source}]:\n{ch.text}" for ch in chunks[:2])
    return lead + "\n" + body


class CustomerAssistant:
    """Bind a company profile to its knowledge base and answer questions."""

    def __init__(
        self,
        profile: CompanyProfile,
        knowledge_base: KnowledgeBase,
        *,
        llm: OllamaClient | None = None,
    ) -> None:
        self.profile = profile
        self.kb = knowledge_base
        self.llm = llm or OllamaClient()

    def answer(self, message: str, *, top_k: int = 4) -> AssistantReply:
        """Answer one customer message, grounded in the company's KB."""
        if not message or not message.strip():
            return AssistantReply(
                answer="Could you tell me a bit more about what you need help with?",
                model="",
            )

        chunks = self.kb.retrieve(message, top_k=top_k)
        citations = [
            Citation(source=ch.source, snippet=_snippet(ch.text)) for ch in chunks
        ]
        escalate = _check_escalation(self.profile, message)
        model = self.profile.effective_model()

        system_prompt = build_system_prompt(self.profile, chunks)
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=message.strip()),
        ]

        try:
            text = self.llm.chat(
                model=model,
                messages=messages,
                temperature=self.profile.llm.temperature,
                max_tokens=self.profile.llm.max_tokens,
            )
            return AssistantReply(
                answer=text,
                citations=citations,
                model=model,
                degraded=False,
                escalate=escalate,
            )
        except OllamaUnavailable as exc:
            logger.warning("LLM unavailable, returning grounded stub: %s", exc)
            return AssistantReply(
                answer=_stub_answer(self.profile, chunks),
                citations=citations,
                model=model,
                degraded=True,
                escalate=escalate,
            )


def _snippet(text: str, *, limit: int = 180) -> str:
    """First ``limit`` chars of a chunk, single-line, for a citation preview."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
