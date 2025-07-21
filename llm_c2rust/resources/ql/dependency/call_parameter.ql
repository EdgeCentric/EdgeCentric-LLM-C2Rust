import cpp

// Calling a function, its parameters' types is needed
from Call c
select c.getLocation().toString(), c.getTarget().getAParameter().getType().getLocation().toString()