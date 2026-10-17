# Issues

Log every bug, error or surprise **when it happens**. Never delete an entry; set its status to resolved.

Template:

```
## ISS-NNN — <short title>  [open | resolved | wontfix]
- When: YYYY-MM-DD HH:MM, step N
- Symptom: <exact error text / observed behaviour>
- Cause: <root cause, or "unknown yet">
- Fix: <what changed, files>
- Verified: <how>
```

---

## Known risks to watch (not yet issues)
- Gemini free-tier RPM/RPD unknown until signup; one interview ≈ 80 LLM calls (~10 RPM).
- Groq `openai/gpt-oss-120b` published limit is 8K TPM, and may be lower on the free plan.
- Sarvam credit: docs say ₹100, the pricing page says ₹1,000.
- Deepgram Nova-3 quality on Hindi–English code-switching not tested.
- The cascade adds ~1 s latency per turn; barge-in must be tested inside the 90-min gate.
- WebRTC through venue NAT: demo from the laptop itself, not a judge's phone.
