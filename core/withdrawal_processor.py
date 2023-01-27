import logging

from django.conf import settings
from django.db.transaction import atomic

from core.models.inouts.sci import GATES
from core.models.inouts.transaction import TRANSACTION_COMPLETED
from core.models.inouts.withdrawal import CREATED
from core.models.inouts.withdrawal import PENDING
from core.models.inouts.withdrawal import WithdrawalRequest


class SCIPayoutsProcessor():
    PROCESS_LIMIT = 50
    STOP_ON_ERROR = False

    def start(self):
        if not settings.PAYOUTS_PROCESSING_ENABLED:
            return
        for request in self.queryset()[:self.PROCESS_LIMIT]:
            try:
                self.process_request(request)
            except Exception:
                logging.error(f'There was an exception durin request #{request.id} processing', exc_info=True)

                if self.STOP_ON_ERROR:
                    raise

    def process_request(self, request: WithdrawalRequest):
        # TODO: better check for race conditions!
        request = request.__class__.objects.get(id=request.id)  # get fresh version
        if request.state == CREATED and request.transaction.state == TRANSACTION_COMPLETED:
            self.update_withdrwal_state(request)
        elif request.state == CREATED:
            self.make_withdrawal(request)
        elif request.state == PENDING:
            self.update_withdrwal_state(request)

    def make_withdrawal(self, obj):
        with atomic():
            obj.change_state(PENDING)
            gate = self.gate(obj)
            obj.txid = str(gate.make_withdrawal(obj))
            # obj.state = PENDING duplicate!! obj.change_state(PENDING)
            obj.save()

    def gate(self, obj: WithdrawalRequest):
        return GATES[obj.sci_gate_id]

    def update_withdrwal_state(self, obj: WithdrawalRequest):
        gate = self.gate(obj)
        gate.update_withdrawal_state(obj)

    def queryset(self):
        return WithdrawalRequest.sci_to_process()
