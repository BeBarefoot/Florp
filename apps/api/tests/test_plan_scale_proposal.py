import cv2
import numpy as np
import pytest

from app.deterministic_blueprint.calibration import dimension_candidates, installed_languages
from app.plan_model import ImageTransform, PlanModel, Scale
from app.plan_scale_proposal import matching_proposal, propose_scale


def sheet(vertical_cm=500):
    image = np.full((620, 820, 3), 255, np.uint8)
    words = []
    for y, end, cm in ((60, 700, 600), (125, 500, 400)):
        cv2.line(image, (100, y), (end, y), (0, 0, 0), 2)
        for x in (100, end):
            cv2.line(image, (x, y - 12), (x, y + 12), (0, 0, 0), 2)
        center = (100 + end) / 2
        words.append({"text": str(cm), "box": [center - 15, y - 28, center + 15, y - 10]})
    cv2.line(image, (760, 70), (760, 570), (0, 0, 0), 2)
    for y in (70, 570):
        cv2.line(image, (748, y), (772, y), (0, 0, 0), 2)
    words.append({"text": str(vertical_cm), "box": [733, 305, 750, 335]})
    return image, words


def test_printed_dimensions_propose_without_setting_metric_scale():
    image, words = sheet()
    proposal = matching_proposal(dimension_candidates(image, words))
    assert proposal and proposal.evidence_count == 3
    assert proposal.reference.length_meters == 6
    assert proposal.check_reference.length_meters == 5
    draft = PlanModel(id="sheet", image_transform=ImageTransform(width=820, height=620),
                      scale=Scale(proposal=proposal))
    assert draft.dump()["scale"]["metersPerPixel"] is None
    draft.scale = Scale(reference=proposal.reference, check_reference=proposal.check_reference)
    assert PlanModel.model_validate(draft.dump()).scale.meters_per_pixel == pytest.approx(.01, rel=.01)


def test_conflicting_axes_or_repeated_labels_do_not_propose_scale():
    image, words = sheet(vertical_cm=420)
    assert matching_proposal(dimension_candidates(image, words)) is None
    image, words = sheet()
    assert matching_proposal(dimension_candidates(image, [words[0]] * 3 + [words[2]])) is None
    assert matching_proposal(dimension_candidates(np.full_like(image, 255), words)) is None


def test_local_ocr_reads_horizontal_and_rotated_dimension_labels():
    if "eng" not in installed_languages():
        pytest.skip("Tesseract English data is optional")
    image, words = sheet()
    for word in words[:2]:
        x, _, _, y = word["box"]
        cv2.putText(image, word["text"], (int(x - 5), int(y)), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 0), 2)
    label = np.full((23, 50, 3), 255, np.uint8)
    cv2.putText(label, "500", (2, 18), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 0), 2)
    image[295:345, 728:751] = cv2.rotate(label, cv2.ROTATE_90_COUNTERCLOCKWISE)
    result = propose_scale(image)
    assert result and {result.reference.length_meters, result.check_reference.length_meters} == {5, 6}
