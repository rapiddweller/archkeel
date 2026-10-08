import 'adapters/memory/in_memory_order_repository.dart';
import 'ordering/application/checkout_service.dart';
import 'ordering/domain/orders/order.dart';
import 'presentation/controller.dart';

const APP_VERSION = '1.0.0';

void main() {
  final repository = InMemoryOrderRepository();
  final checkout = CheckoutService(repository);
  final controller = CheckoutController(checkout);
  final order = Order('order-1', lines: const [OrderLine('sku-1', 2, 1250)]);
  controller.submit(CheckoutRequest('request-1', [OrderLine('sku-2', 1, 500)]));
  repository.save(order);
}
