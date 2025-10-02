from database_api import BaseEnum


class UserRole(BaseEnum):
  ADMIN = 'Admin'
  CUSTOMER = 'Customer'
  OPERATOR = 'Operator'
  DELIVERY = 'Delivery'


class OrderStatus(BaseEnum):
  PENDING = 'Pending'
  IN_PROGRESS = 'In Progress'
  ON_BOARD = 'On Board'
  COMPLETED = 'Completed'
  CANCELLED = 'Cancelled'
  AT_WAREHOUSE = 'At Warehouse'
  TO_RESCHEDULE = 'Da Riprogrammare'


class OrderType(BaseEnum):
  DELIVERY = 'Delivery'
  WITHDRAW = 'Withdraw'
  REPLACEMENT = 'Replacement'
  CHECK = 'Check'
