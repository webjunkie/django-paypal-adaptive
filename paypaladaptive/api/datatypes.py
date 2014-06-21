from .errors import ReceiverError


class Receiver(object):
    email = None
    amount = None
    primary = False

    def __init__(self, email=None, amount=None, primary=False):
        self.email = email
        self.amount = amount
        self.primary = primary

    def to_dict(self):
        return {'email': self.email,
                'amount': self.amount,
                'primary': self.primary}

    def __unicode__(self):
        return self.email


class ReceiverList(object):
    receivers = None

    def __init__(self, receivers=None):
        self.receivers = []
        if receivers is not None:
            for receiver in receivers:
                self.append(receiver)

        self.validate()

    def append(self, receiver):
        if not isinstance(receiver, Receiver):
            raise ReceiverError("receiver needs to be instance of Receiver")
        self.receivers.append(receiver)

    def to_dict(self):
        self.has_primary()
        return [r.to_dict() for r in self.receivers]

    def __len__(self):
        return len(self.receivers)

    def has_primary(self):
        n_primary = len(filter(lambda r: r.primary is True, self.receivers))

        if n_primary > 1:
            raise ReceiverError("There can only be one primary Receiver.")

        return n_primary == 1

    @property
    def chained(self):
        return self.has_primary()

    @property
    def total_amount(self):
        return sum([r.amount for r in self.receivers])

    def validate_receiver_length(self):
        if len(self.receivers) > 6:
            raise ReceiverError("The maximum length of receivers is 6.")
        return True

    def validate(self):
        # check if there is only one primary receiver
        self.has_primary()
        self.validate_receiver_length()
