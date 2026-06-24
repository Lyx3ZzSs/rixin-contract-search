from __future__ import annotations


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _as_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {}


def _case_expected_included(case: dict) -> set[str]:
    case_dict = _as_dict(case)
    expected = _as_dict(case_dict.get("expected"))
    included = expected.get("included") or []
    if not isinstance(included, (list, tuple, set)):
        return set()
    return {str(document_uri) for document_uri in included if document_uri is not None and str(document_uri)}


def _case_actual_predictions(case: dict) -> list[dict]:
    case_dict = _as_dict(case)
    actual = case_dict.get("actual") or []
    predictions: list[dict] = []
    for prediction in actual:
        prediction_dict = _as_dict(prediction)
        if prediction_dict:
            predictions.append(prediction_dict)
    return predictions


def _prediction_support_rate(prediction: dict) -> float:
    prediction_dict = _as_dict(prediction)
    try:
        support_rate = float(prediction_dict.get("evidence_support_rate") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if support_rate < 0.0 or support_rate > 1.0:
        return 0.0
    return support_rate


def compute_eval_metrics(cases: list[dict], schema_failures: int = 0, verification_failures: int = 0) -> dict[str, float]:
    schema_failures = max(0, schema_failures)
    verification_failures = max(0, verification_failures)
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
        predicted_included_uris = set()
        for prediction in predictions:
            decision = str(prediction.get("decision") or "")
            if decision == "included":
                document_uri = str(prediction.get("document_uri") or "")
                if document_uri:
                    predicted_included_uris.add(document_uri)
                support_total += _prediction_support_rate(prediction)
                support_count += 1
            elif decision == "uncertain":
                uncertain_predictions += 1
        predicted_included += len(predicted_included_uris)
        true_positive += len(predicted_included_uris & expected_included)

    return {
        "precision": _safe_divide(true_positive, predicted_included),
        "recall": _safe_divide(true_positive, expected_included_total),
        "uncertain_rate": _safe_divide(uncertain_predictions, total_predictions),
        "evidence_support_rate": _safe_divide(support_total, support_count),
        "schema_failure_rate": _safe_divide(schema_failures, max(1, total_cases)),
        "verification_failure_rate": _safe_divide(verification_failures, max(1, total_cases)),
    }
