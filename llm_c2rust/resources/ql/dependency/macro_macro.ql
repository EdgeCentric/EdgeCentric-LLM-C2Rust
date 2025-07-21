import cpp


// Macro dependency: macro depends something if all invocation contains another macro's invocation
from Macro trg, Macro src
where forex(MacroInvocation mi | mi = src.getAnInvocation() | trg.getAnInvocation().getParentInvocation() = mi)
select src.getLocation().toString(),  trg.getLocation().toString()