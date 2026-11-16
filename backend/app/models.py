from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_url: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/completed/failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    findings: Mapped[list["Finding"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")

class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))
    tool: Mapped[str] = mapped_column(String(30))        # ruff / bandit / radon / pip-audit
    category: Mapped[str] = mapped_column(String(30))    # quality / bug / security / complexity / dependency
    severity: Mapped[str] = mapped_column(String(10))    # low / medium / high
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped["Analysis"] = relationship(back_populates="findings")