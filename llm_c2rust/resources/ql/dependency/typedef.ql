import cpp

// Typedef Type depends on the original one
from TypedefType src, Type trg
where trg = src.stripType()
select src.getLocation().toString(), trg.getLocation().toString()