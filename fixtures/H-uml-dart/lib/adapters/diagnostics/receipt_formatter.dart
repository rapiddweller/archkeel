import '../../ordering/domain/orders/order.dart';

const String RECEIPT_PREFIX = 'Order';

String formatReceipt(Order order) =>
    '$RECEIPT_PREFIX ${order.id}: ${order.total()}';
