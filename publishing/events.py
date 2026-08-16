from django.dispatch import Signal

# All signals are emitted inside the domain-service transaction, after the public
# snapshot and its many-to-many topics are complete. Receiver writes therefore
# roll back together with a failed publish operation.
content_published = Signal()
content_unpublished = Signal()
content_removed = Signal()
content_restored = Signal()
