# Optional image pixel detector

FANILO's image endpoint works without an external detector: it checks file metadata and generator
markers and offers reverse-search links. It does not infer authenticity from their absence, and
detecting a Content Credentials structure does not verify its signature.

## Service contract

An operator may configure a self-hosted detector or a server-side adapter for a specialized
provider. There is no provider account, paid service or model enabled by this repository.

```dotenv
IMAGE_DETECTOR_URL=https://your-service.example/analyze
IMAGE_DETECTOR_TOKEN=
IMAGE_DETECTOR_VALIDATED=false
```

Until `IMAGE_DETECTOR_VALIDATED=true`, **no image is sent to that service**. It is an explicit
operational gate, not an automatic certification or evidence that an evaluation has happened.

When enabled, FANILO sends:

- `POST` to the configured URL; HTTPS required, except HTTP on localhost for local development.
- `Content-Type`: the actual raster image MIME type detected by Pillow.
- Body: original image bytes, including any embedded metadata. Never forward confidential images
  without considering the provider's retention and data-use policies.
- Optional `Authorization: Bearer <IMAGE_DETECTOR_TOKEN>`; the credential stays on the API server.

The service must respond within 20 seconds, without redirecting, with at most 16 KB of JSON:

```json
{"ai_score": 0.94, "model": "detector-name/version"}
```

`ai_score` is a finite number from 0 to 1. It is **not** a calibrated probability that the image
is fake. Operational cutoffs: ≥0.9 flags a possible generation signal; ≤0.1 finds no signal;
everything between is inconclusive. The score itself is not exposed as a confidence percentage.
Invalid replies, redirects, timeouts and service errors leave the pixel result unavailable;
FANILO still returns the metadata with appropriate uncertainty.

## Evaluate before enabling

Use an independently labelled set with known provenance, not the detector's own examples:

1. Camera photographs, generated images from several generators, edited photos and illustrations.
2. For each category, include original files and realistic resized, cropped, screenshot and
   recompressed variants. Include the kinds of Facebook/WhatsApp images newsrooms actually receive.
3. Measure false positives on human-created images, missed generated images and abstentions at
   the deployed cutoffs, separately for each format and transformation. Do not report accuracy
   only on a balanced, uncompressed showcase set.
4. Record dataset provenance, sizes, detector/model version, date, failure cases and review decision.
   Do not enable a model that cannot distinguish uncertainty or that systematically accuses real
   photos. Re-evaluate after a model update.
5. Review terms, retention, cost, availability and the user-facing transmission notice before
   setting the validation flag.

Even after evaluation, keep the fallibility warning and evidence visible. A journalist must
corroborate the result; image origin and the truth of its caption are separate questions.
