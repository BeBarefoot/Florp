# Segmentation source-coordinate correction

The Ultralytics adapter currently resizes masks.data directly to the original
image size. Default inference masks can include letterbox padding. Stretching
them can displace structural walls on a non-square source.

Implementation: request retina_masks=True, require the result original dimensions
and mask dimensions to match the caller's source raster, validate finite mask
values and one mask per detected object, and reject mismatches instead of guessing
an inverse transform. Leave the separate Yytsi raster transform unchanged.

Tests: non-square mask retains exact occupied pixels; inference receives the
native-mask request; padded mask, wrong source dimensions, missing masks and
nonfinite values fail explicitly. Run the complete backend suite and CI.

Primary contract: https://docs.ultralytics.com/modes/predict/#inference-arguments
retina_masks returns masks.data at the original image dimensions. This fixes an
adapter coordinate contract, not the underlying model's detection accuracy.
