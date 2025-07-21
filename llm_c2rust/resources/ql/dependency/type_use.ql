import cpp

// Whenever a type is used
from Type trg, Expr src
where trg = src.getType()
select src.getLocation().toString(), trg.getLocation().toString()