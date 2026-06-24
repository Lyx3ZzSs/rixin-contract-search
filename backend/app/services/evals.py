from __future__ import annotations

def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _case_expected_included(case: dict) -> set[str]:
    expected = case.get("expected") or {}
    included = expected.get("included") or []
    return {str(document_uri) for document_uri in included}


def _case_actual_predictions(case: dict) -> list[dict]:
    actual = case.get("actual") or []
    return [prediction for prediction in actual if isinstance(prediction, dict)]


def compute_eval_metrics(cases: list[dict], schema_failures: int = 0, verification_failures: int = 0) -> dict[str, float]:
    total_cases = len(cases)
    total_predictions = 0
    predicted_included = 0
    true_positive = 0
    uncertain_predictions = 0
    support_total = 0.0
    support_count = 0
    expected_included_total = 0

    for case in cases:
        expected_included = _case_expected_included(case)
        expected_included_total += len(expected_included)
        predictions = _case_actual_predictions(case)
        total_predictions += len(predictions)
        for prediction in predictions:
            decision = str(prediction.get("decision") or "")
            if decision == "included":
                predicted_included += 1
                document_uri = str(prediction.get("document_uri") or "")
                if document_uri in expected_included:
                    true_positive += 1
                support_total += float(prediction.get("evidence_support_rate") or 0.0)
                support_count += 1
            elif decision == "uncertain":
                uncertain_predictions += 1

    return {
        "precision": _safe_divide(true_positive, predicted_included),
        "recall": _safe_divide(true_positive, expected_included_total),
        "uncertain_rate": _safe_divide(uncertain_predictions, total_predictions),
        "evidence_support_rate": _safe_divide(support_total, support_count),
        "schema_failure_rate": _safe_divide(schema_failures, max(1, total_cases)),
        "verification_failure_rate": _safe_divide(verification_failures, max(1, total_cases)),
    }
