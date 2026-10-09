from typing import Literal
from pydantic import BaseModel, Field, field_validator

ROLES = ('defesa', 'oposicao', 'verificador', 'juiz')
TERMINAL = {'completed', 'cancelled', 'interrupted'}

class Speech(BaseModel):
    text: str = Field(min_length=1)

    @field_validator('text')
    @classmethod
    def word_limit(cls, value):
        if len(value.split()) > 180:
            raise ValueError('Cada fala deve ter até 180 palavras.')
        return value

class Claim(BaseModel):
    text: str = Field(min_length=1, max_length=700)
    role: Literal['defesa', 'oposicao']
    query: str = Field(min_length=1, max_length=350)

class Claims(BaseModel):
    claims: list[Claim] = Field(max_length=3)

class Verification(BaseModel):
    status: Literal['confirmada', 'contradita', 'inconclusiva']
    explanation: str = Field(min_length=1)
    source_ids: list[int]

class Proposal(Speech):
    conclusion: str = Field(min_length=1, max_length=1500)
    answers_question: bool

class Acceptance(Speech):
    accepted: bool
    conclusion: str = Field(min_length=1)

class Confirmation(Speech):
    confirmed: bool
    conclusion: str

class Score(BaseModel):
    evidencias: float = Field(ge=0, le=10)
    coerencia: float = Field(ge=0, le=10)
    refutacoes: float = Field(ge=0, le=10)
    justification: str = Field(min_length=1)

class Verdict(Speech):
    conclusion: str = Field(min_length=1)
    justification: str = Field(min_length=1)
    divergences: list[str]
    scores: dict[Literal['defesa', 'oposicao'], Score]

    @field_validator('scores')
    @classmethod
    def both_scores(cls, value):
        if set(value) != {'defesa', 'oposicao'}:
            raise ValueError('O julgamento deve avaliar os dois debatedores.')
        return value

class MatchRequest(BaseModel):
    question: str = Field(min_length=8, max_length=2000)
    models: dict[str, str]

    @field_validator('models')
    @classmethod
    def all_roles(cls, value):
        if set(value) != set(ROLES):
            raise ValueError('Selecione um modelo para cada um dos quatro papéis.')
        return value

def consensus_valid(proposal, acceptances):
    return bool(proposal['answers_question'] and all(
        acceptances[r]['accepted'] is True and
        acceptances[r]['conclusion'] == proposal['conclusion']
        for r in ('defesa', 'oposicao')
    ))
