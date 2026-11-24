"""Map temporary raster extraction geometry back to the source canvas."""

from .plan_model import ImageTransform, PlanModel
from .plan_workspace import Document


class ExtractionResize:
    def __init__(self, width, height, factor):
        self.width = width
        self.height = height
        self.factor = factor

    def point(self, point):
        # OpenCV resize samples pixel centers.
        point.x = min(self.width, max(0, (point.x + 0.5) / self.factor - 0.5))
        point.y = min(self.height, max(0, (point.y + 0.5) / self.factor - 0.5))

    def model(self, model):
        for node in model.nodes:
            self.point(node)
        for wall in model.walls:
            wall.thickness_px /= self.factor
        for opening in model.openings:
            opening.offset_px /= self.factor
            opening.width_px /= self.factor
            for point in opening.span or ():
                self.point(point)
        for room in model.rooms:
            room.area_px2 /= self.factor**2
            for point in room.polygon:
                self.point(point)
        for point in model.envelope or ():
            self.point(point)
        for symbol in model.room_symbols:
            self.point(symbol.position)
        for finding in model.findings:
            self.point(finding.anchor)
            if finding.closure:
                self.point(finding.closure.start)
                self.point(finding.closure.end)
                finding.closure.thickness_px /= self.factor
        model.image_transform = ImageTransform(width=self.width, height=self.height)
        return PlanModel.model_validate(model.dump())

    def document(self, document):
        # Raw wall and door segments may share point objects. Map each into
        # its own copy so an endpoint is never transformed twice.
        for segment in document.objects + document.wall_returns:
            segment.start = segment.start.model_copy()
            segment.end = segment.end.model_copy()
            self.point(segment.start)
            self.point(segment.end)
            segment.thickness_px /= self.factor
        for point in (document.envelope or []) + document.passages:
            self.point(point)
        document.width, document.height = self.width, self.height
        return Document.model_validate(document.model_dump())
