import type { Order } from "../domain/order";

export interface OrderPayload {
  readonly id: string;
  readonly requestId: string;
}

export function toOrder(payload: OrderPayload): Order {
  return { id: payload.id };
}
