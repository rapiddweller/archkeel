import 'package:shop/domain/orders/order.dart';

abstract interface class OrderRepository {
  Future<Order> place(Order order);

  Future<List<Order>> loadAll();

  Stream<List<Order>> watchAll();

  Future<Order?> findById(String id);
}
