import 'package:shop/data/services/demo_backend.dart';
import 'package:shop/data/services/memory_store.dart';
import 'package:shop/domain/orders/order.dart';
import 'package:shop/domain/orders/order_repository.dart';

class MemoryOrderRepository implements OrderRepository {
  MemoryOrderRepository(this._backend, this._store);

  final DemoBackend _backend;
  final MemoryStore _store;

  @override
  Future<Order> place(Order order) async {
    final saved = await _backend.submitOrder(order);
    _store.saveOrders([..._store.readOrders(), saved]);
    return saved;
  }

  @override
  Future<List<Order>> loadAll() async {
    if (!_backend.isOnline()) return _store.readOrders();
    final remote = await _backend.fetchOrders();
    final local = _store.readOrders();
    final orders = [
      ...remote,
      ...local.where((order) => !remote.any((item) => item.id == order.id)),
    ];
    _store.saveOrders(orders);
    return orders;
  }

  @override
  Stream<List<Order>> watchAll() => _store.watchOrders();

  @override
  Future<Order?> findById(String id) async {
    return _store.findOrder(id);
  }
}
