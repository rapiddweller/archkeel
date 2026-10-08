import 'package:shop/domain/catalog/product.dart';

class CartLine {
  const CartLine(this.product, this.quantity);

  final Product product;
  final int quantity;

  int get lineTotalCents => product.priceCents * quantity;
}

class Cart {
  Cart();

  final List<CartLine> _lines = [];

  List<CartLine> get lines => List.unmodifiable(_lines);

  int get totalCents =>
      _lines.fold(0, (sum, line) => sum + line.lineTotalCents);

  void add(Product product) {
    final index = _lines.indexWhere((line) => line.product.id == product.id);
    if (index < 0) {
      _lines.add(CartLine(product, 1));
    } else {
      _lines[index] = CartLine(product, _lines[index].quantity + 1);
    }
  }

  void setQuantity(String productId, int quantity) {
    final index = _lines.indexWhere((line) => line.product.id == productId);
    if (index < 0) return;
    if (quantity <= 0) {
      _lines.removeAt(index);
    } else {
      _lines[index] = CartLine(_lines[index].product, quantity);
    }
  }

  void remove(String productId) =>
      _lines.removeWhere((line) => line.product.id == productId);

  void clear() => _lines.clear();
}
