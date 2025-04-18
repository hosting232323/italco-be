from database_api import BaseEnum

class UserRole(BaseEnum):
  ADMIN = 'Admin'
  CUSTOMER = 'Customer'
  OPERATOR = 'Operator'
  DELIVERY = 'Delivery'
