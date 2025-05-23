from database_api import BaseEnum

class UserRole(BaseEnum):
  ADMIN = 'Admin'
  CUSTOMER = 'Customer'
  OPERATOR = 'Operator'
  DELIVERY = 'Delivery'

class OrderStatus(BaseEnum):
  PENDING = 'Pending'
  IN_PROGRESS = 'In Progress'
  COMPLETED = 'Completed'
  CANCELLED = 'Cancelled'
  ANOMALY = 'Anomaly'
  DELAY = 'Delay'

class OrderType(BaseEnum):
  DELIVERY = 'Delivery'
  WITHDRAW = 'Withdraw'
  REPLACEMENT = 'Replacement'
  CHECK = 'Check'
