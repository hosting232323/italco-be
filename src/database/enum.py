import enum


class UserRole(enum.Enum):
  ADMIN = 'Admin'
  CUSTOMER = 'Customer'
  OPERATOR = 'Operator'
  DELIVERY = 'Delivery'


class OrderStatus(enum.Enum):
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
  # No Api
  AT_WAREHOUSE = 'At Warehouse'
  TO_RESCHEDULE = 'To Reschedule'


class OrderType(enum.Enum):
  DELIVERY = 'Delivery'
  WITHDRAW = 'Withdraw'
  REPLACEMENT = 'Replacement'
  CHECK = 'Check'


class ScheduleType(enum.Enum):
  ORDER = 'Order'
  COLLECTIONPOINT = 'CollectionPoint'
