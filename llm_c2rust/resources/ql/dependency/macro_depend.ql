import cpp
import semmle.code.cpp.commons.Dependency

// Macro dependency: macro depends something if all invocation of this macro depends on something
from Symbol trg,  Location trg_loc, Macro src
where  forex(MacroInvocation mi | mi = src.getAnInvocation() | trg.getADependentElement(1) = mi.getAnExpandedElement()) and 
        src != trg and
        (if trg instanceof DeclarationEntry 
            then trg_loc = trg.(DeclarationEntry).getDeclaration().getLocation() 
            else trg_loc = trg.getLocation()) 
select src.getLocation().toString(), trg_loc.toString()