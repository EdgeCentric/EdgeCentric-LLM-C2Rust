import cpp
import semmle.code.cpp.commons.Dependency
// Simple dependency
from Symbol trg,  Location trg_loc, Element src
where 
    (if trg instanceof DeclarationEntry 
        then trg_loc = trg.(DeclarationEntry).getDeclaration().getLocation() 
        else trg_loc = trg.getLocation()) 
    and src = trg.getADependentElement(1)
select src.getLocation().toString(), trg_loc.toString()