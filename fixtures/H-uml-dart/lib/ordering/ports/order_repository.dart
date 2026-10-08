import '../domain/orders/order.dart';

abstract interface class OrderRepository {
  void save(Order order);
  Order? findById(String id);
}
