"""Bounded transaction identity, not a durable Neo4j element-ID locator."""

import time
from contextlib import contextmanager
from uuid import uuid4

from neo4j import READ_ACCESS
from neo4j.exceptions import DriverError, Neo4jError

from agent_native_graph.domain.entities import EntityPayload, EntityReference


class StaleWorkflowError(ValueError):
    """The workflow cannot safely resolve its entities; start a fresh workflow."""


class TransactionIdentity:
    """Keep element references inside one transaction, invalidating rather than rebinding."""

    def __init__(self, driver, database, timeout_s, clear):
        self.driver, self.database, self.timeout_s = driver, database, timeout_s
        self.owner = uuid4().hex
        self.clear = clear
        self.session = self.transaction = None
        self.started = None
        self.invalid = False
        self.closed = False
        self.keys = set()

    def check(self):
        """Reject expired/closed workflows before local operations as well as queries."""
        if self.invalid or self.closed:
            raise StaleWorkflowError("Entity workflow is invalid; create a new workflow/session")
        if self.started is not None and time.monotonic() - self.started >= self.timeout_s:
            self.invalidate("Entity workflow timed out")

    def invalidate(self, reason):
        """Discard handles and terminate the transaction without an automatic retry."""
        self.invalid = True
        self.clear()
        try:
            self.close()
        finally:
            raise StaleWorkflowError(reason + "; create a new workflow/session")

    def close(self):
        """Roll back the read transaction and release its session, idempotently."""
        self.closed = True
        self.keys.clear()
        transaction, session = self.transaction, self.session
        self.transaction = self.session = None
        try:
            if transaction is not None:
                transaction.rollback()
        finally:
            if session is not None:
                session.close()

    @contextmanager
    def scope(self):
        """A failed transaction is terminal, while argument errors remain repairable."""
        self.check()
        try:
            yield
        except (Neo4jError, DriverError) as exc:
            self.invalidate(f"Entity transaction failed ({type(exc).__name__})")

    @contextmanager
    def queries(self):
        self.check()
        if self.transaction is None:
            options = {"default_access_mode": READ_ACCESS}
            if self.database is not None:
                options["database"] = self.database
            self.session = self.driver.session(**options)
            try:
                self.transaction = self.session.begin_transaction(timeout=self.timeout_s)
                self.started = time.monotonic()
            except Exception:
                self.session.close()
                self.session = None
                raise
        if self.transaction.closed():
            self.invalidate("Entity transaction was closed")
        yield self.transaction

    def reference(self, node):
        """Capture an element ID only while its owning transaction is active."""
        self.check()
        if self.transaction is None or not isinstance(node.element_id, str) or not node.element_id:
            raise StaleWorkflowError("Cannot create an entity reference outside its transaction")
        self.keys.add(node.element_id)
        return EntityReference(self.owner, node.element_id)

    def key(self, payload):
        """Resolve an internal reference, never a user property or another workflow's ID."""
        self.check()
        if not isinstance(payload, EntityPayload) or payload.reference.owner != self.owner:
            raise ValueError("Entity reference belongs to another workflow or has no provenance")
        return payload.reference.key

    def validate(self, handles):
        """Detect deleted bound nodes before using even locally cached rows."""
        bound = {
            self.key(value)
            for handle in handles
            for row in handle.rows
            for value in row.values()
            if isinstance(value, EntityPayload)
        }
        # Metadata-only/count handles may retain ancestor query parameters but
        # no node rows. Validate all observed identities, not just visible rows.
        keys = self.keys | bound
        if not keys:
            return
        with self.queries() as tx:
            actual = {
                row["key"]
                for row in tx.run(
                    "MATCH (n) WHERE elementId(n) IN $keys RETURN elementId(n) AS key",
                    keys=sorted(keys),
                )
            }
        if actual != keys:
            self.invalidate("A referenced node was deleted or is no longer visible")
