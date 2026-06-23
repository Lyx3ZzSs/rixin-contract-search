import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.enums import ArtifactType
from app.models import ContractFile, ParsedArtifact
from app.services.parsing.unified_parser_client import ParseResult
from app.services.storage import parsed_dir, qmd_docs_dir, remove_path


def write_artifacts(session: Session, contract: ContractFile, response: ParseResult, provider: str) -> None:
    base = parsed_dir(contract.task_id)
    tmp_dir = base / f"{contract.id}.tmp"
    final_dir = base / str(contract.id)
    qmd_final = qmd_docs_dir(contract.task_id) / f"{contract.id}.md"
    remove_path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        contract_md = tmp_dir / "contract.md"
        contract_md.write_text(response.contract_markdown, encoding="utf-8")
        session.add(ParsedArtifact(contract_id=contract.id, artifact_type=ArtifactType.contract_markdown.value, page_number=0, stored_path=str(final_dir / "contract.md"), parser_name=response.parser_name, parser_version=response.parser_version))

        pages_dir = tmp_dir / "pages"
        pages_dir.mkdir()
        qmd_parts: list[str] = []
        for page in sorted(response.pages, key=lambda p: p.page_number):
            page_path = pages_dir / f"{page.page_number:03d}.md"
            page_path.write_text(page.markdown, encoding="utf-8")
            session.add(ParsedArtifact(contract_id=contract.id, artifact_type=ArtifactType.page_markdown.value, page_number=page.page_number, stored_path=str(final_dir / "pages" / page_path.name), parser_name=response.parser_name, parser_version=response.parser_version))
            if page.markdown.strip():
                qmd_parts.append(f"<!-- page:{page.page_number} -->\n{page.markdown}")
        metadata_path = tmp_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "parser_name": response.parser_name,
                    "parser_version": response.parser_version,
                    "provider_request_id": response.provider_request_id,
                    "provider": provider,
                    "quality": response.quality,
                    "metadata": response.metadata,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        session.add(ParsedArtifact(contract_id=contract.id, artifact_type=ArtifactType.metadata_json.value, page_number=0, stored_path=str(final_dir / "metadata.json"), parser_name=response.parser_name, parser_version=response.parser_version))

        evidence_path = tmp_dir / "evidence.json"
        evidence_path.write_text(json.dumps([e.model_dump() for e in response.evidence], ensure_ascii=False), encoding="utf-8")
        session.add(ParsedArtifact(contract_id=contract.id, artifact_type=ArtifactType.evidence_json.value, page_number=0, stored_path=str(final_dir / "evidence.json"), parser_name=response.parser_name, parser_version=response.parser_version))

        if not qmd_parts:
            qmd_parts = [f"<!-- page:1 -->\n{response.contract_markdown}"]
        qmd_doc = tmp_dir / "qmd_doc.md"
        qmd_doc.write_text(
            f"---\ntask_id: {contract.task_id}\ncontract_id: {contract.id}\nfile_name: {contract.original_filename}\n---\n\n" + "\n\n".join(qmd_parts),
            encoding="utf-8",
        )
        session.flush()
        remove_path(final_dir)
        os.replace(tmp_dir, final_dir)
        os.replace(final_dir / "qmd_doc.md", qmd_final)
    except Exception:
        remove_path(tmp_dir)
        remove_path(final_dir)
        remove_path(qmd_final)
        raise
