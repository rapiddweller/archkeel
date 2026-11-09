import { Greeting } from "@app";
import fs = require("fs");
const lazy = () => import("./util/format");
const config = require("./util/format");
export { Greeting, lazy, config, fs };
export type Shown = import("./util/format").Label;
