import enum


class UserRole(enum.Enum):
  ADMIN = 'Admin'
  CUSTOMER = 'Customer'
  OPERATOR = 'Operator'
  DELIVERY = 'Delivery'


class OrderStatus(enum.Enum):
  ACQUIRED = 'Acquired'
  BOOKED = 'Booked'
  SCHEDULED = 'Scheduled'
  BOOKING = 'Booking'
  DELIVERED = 'Delivered'
  NOT_DELIVERED = 'Not Delivered'
  TO_RESCHEDULE = 'To Reschedule'
  RESCHEDULED = 'Rescheduled'


class RaeStatus(enum.Enum):
  GENERATED = 'Generated'
  EMITTED = 'Emitted'
  LDR = 'LDR'
  DISPOSED_OFF = 'Disposed Off'
  ANNULLED = 'Annulled'


class RaeStatus(enum.Enum):
  GENERATED = 'Generated'
  EMITTED = 'Emitted'
  LDR = 'LDR'
  DISPOSED_OFF = 'Disposed Off'
  ANNULLED = 'Annulled'


class EuronicsStatus(enum.Enum):
  NEW = 'New'
  CONFIRMED = 'Confirmed'
  BOOKING = 'Booking'
  DELIVERED = 'Delivered'
  NOT_DELIVERED = 'Not Delivered'
  REDELIVERY = 'Redelivery'
  REPLACEMENT = 'Replacement'
  CANCELLED = 'Cancelled'
  URGENT = 'Urgent'
  VERIFICATION = 'Verification'
  CANCELLED_TO_BE_REFUNDED = 'Cancelled to be Refunded'
  DELETED = 'Deleted'


class OrderType(enum.Enum):
  DELIVERY = 'Delivery'
  WITHDRAW = 'Withdraw'
  REPLACEMENT = 'Replacement'
  CHECK = 'Check'


class ScheduleType(enum.Enum):
  ORDER = 'Order'
  COLLECTIONPOINT = 'CollectionPoint'
