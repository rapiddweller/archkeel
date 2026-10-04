// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

import type { OrderRepository } from "../domain";
export async function page(repository: OrderRepository): Promise<string> {
  return (await repository.load()).map(order => order.id).join(", ");
}
