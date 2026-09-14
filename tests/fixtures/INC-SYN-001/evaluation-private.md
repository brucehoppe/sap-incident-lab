# Evaluation answer key — INC-SYN-001 (synthetic)

**Not read by the server. Kept beside the fixture only for test authoring;
mirrors the real-incident rule in DESIGN.md section 5 (evaluation-private
never gets configured into INCIDENT_LAB_ROOT).**

Known cause: a background job (`BATCH_SYN`) held an enqueue lock on
`/SYN/CI_INCIDENT` and was killed (SIGTERM) without releasing it. The lock
survived the work-process restart. The subsequent transport import's
activation phase could not get the lock, timed out, and the object
`/SYN/CI_INCIDENT` was left inactive, producing return code 8.

A correct investigation should surface both files as relevant, connect the
timestamps (09:31:40–09:31:41 lock/termination in the trace vs. 09:31:18–
09:33:44 in the import log), and flag the stale lock as the leading
hypothesis — with "check the enqueue table for orphaned locks on this
object" as a next step.
