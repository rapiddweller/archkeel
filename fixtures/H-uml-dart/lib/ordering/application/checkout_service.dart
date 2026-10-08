import '../domain/orders/order.dart';
import '../ports/order_repository.dart';

class CheckoutService {
  CheckoutService(OrderRepository repository) : _repository = repository;

  final OrderRepository _repository;

  String checkout(Order order, {String requestId = 'local'}) {
    order.place();
    _repository.save(order);
    final receiptId = order.id;
    return '$requestId:$receiptId:${order.total()}';
  }
}
