use std::io::{self, Read};

use _core::collect_import_batch_json;

fn target_argument() -> Result<String, ()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.as_slice() {
        [] => Ok("3.11".to_owned()),
        [flag, target] if flag == "--target" => Ok(target.clone()),
        _ => Err(()),
    }
}

fn main() {
    let Ok(target) = target_argument() else {
        std::process::exit(2);
    };
    let mut source = String::new();
    if io::stdin().read_to_string(&mut source).is_err() {
        std::process::exit(2);
    }
    match collect_import_batch_json(&source, &target) {
        Ok(batch) => println!("{batch}"),
        Err(_) => std::process::exit(2),
    }
}
