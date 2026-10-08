import '../../ordering/domain/orders/order.dart';
import '../../ordering/ports/order_repository.dart';

class InMemoryOrderRepository implements OrderRepository {
  InMemoryOrderRepository();

  final Map<String, Order> _orders = {};

  @override
  void save(Order order) => _orders[order.id] = order;

  @override
  Order? findById(String id) => _orders[id];
}
