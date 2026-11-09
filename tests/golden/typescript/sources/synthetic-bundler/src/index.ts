import logo from "./assets/logo.svg";
import { total } from "@/cart";
import { missing } from "@/nowhere";

export const view = `${logo}:${total([1, 2])}:${missing}`;
