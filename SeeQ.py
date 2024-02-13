#%% 
''' 
SeeQ is basically a python library that provides a set of classes and functions to support:
1. Specifying CQs,
2. Authoring Applications (as functions) reusing CQs
3. Resolving (over graph inputs) and Executing (over dataframes) Applications --> Using only one function: "resolve"

Classes: 
-        CQ: Master CQ class
-   GraphCQ: CQ Subclass representing how a CQ can be found in a graph (implemented as a SHACL shape) 
- VirtualCQ: CQ Subclass representing computations 
- DefaultCQ: CQ Subclass representing default values or thresholds
-    CalcCQ : Only used internally to perform calculations between CQ objects

Functions: 
-       batched: Gabe's technicality
-       get_cqs: Used internally to return the CQs of each application
- is_applicable: Checking whether CQs can be found in a graph
-       resolve: Used to resolve and execute each application
'''
from functools import partial
from itertools import islice
from collections import defaultdict
import inspect
from typing import Tuple, Callable, List, Dict
from rdflib import Namespace, Graph, BNode, Literal, URIRef
from rdflib.term import Node
from dataclasses import dataclass, field
from shape_to_query import shape_to_query
import pyshacl
from typing import Literal, Tuple, Callable
from rdflib import Namespace, Graph, BNode, Literal, URIRef
import numpy as np
from sympy import*
from rdflib.collection import Collection
from rdflib.paths import AlternativePath, SequencePath
from dataclasses import dataclass, field
import pyshacl

# Definition of namespaces
BRICK = Namespace("https://brickschema.org/schema/Brick#")
APAR = Namespace("http://openmetrics.eu/openmetrics/apar#")
OM = Namespace("http://openmetrics.eu/openmetrics#")
SH = Namespace("http://www.w3.org/ns/shacl#")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
GCQ = Namespace("https://brickschema.org/schema/Brick/GraphCQ#") #used to represent the shape of a CQ.
UNIT = Namespace("http://qudt.org/vocab/unit#")
QUDT = Namespace("https://qudt.org/2.1/schema/datatype")
REF = Namespace("https://brickschema.org/schema/Brick/ref#")
BACNET = Namespace("https://brickschema.org/schema/Bacnet")
A = RDF.type

@dataclass
class CQ:
    '''
    This is the master class used to define CQ objects. 
    A CQ object has three attributes:
    (1) description, 
    (2) unit, 
    (3) implementation which is a list of possible resolutions

    The following functions are called "magic" and they are used
    to perform calculations between CQ objects and numbers.
    '''
    description: str
    unit: UNIT.unit
    implementation: list

    def __post_init__(self):
        self.value = np.NaN
        self.description = self.description.replace(" ", "_")

    def __add__(self, other):
        '''
        A magic function performing addition between CQ objects or numbers. 
        The implementation is slightly weird: 
        
        Every time a magic function is used, a "Calc" object is created which
        can store the value that we want to retrieve. 
        The function returns a Calc object which can then be reused to perform
        another calculation. For example: 
        Tma + Tsa + Tra is performed as (1) Tma + Tsa -> returns a Calc object 
        with value 100, (2) 100 + Tra returns again a Calc object. 

        In this way, we can use CQ objects in equations.       
        Calc objects are designed be used for calculations (check below). 
        '''
        r = Calc(self, other)
        r.value = r.cq1val + r.cq2val
        return r

    def __radd__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val + r.cq2val
        return r

    def __sub__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val - r.cq2val
        return r

    def __rsub__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val - r.cq2val
        return r

    def __mul__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val * r.cq2val
        return r

    def __rmul__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val * r.cq2val
        return r

    def __truediv__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val / r.cq2val
        return r

    def __rtruediv__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val / r.cq2val
        return r

    def __lt__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val < r.cq2val
        return r

    def __rlt__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val < r.cq2val
        return r

    def __le__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val <= r.cq2val
        return r

    def __rle__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val <= r.cq2val
        return r

    def __gt__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val > r.cq2val
        return r

    def __rgt__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val > r.cq2val
        return r

    def __ge__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val >= r.cq2val
        return r

    def __rge__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val >= r.cq2val
        return r

    def __and__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val and r.cq2val
        return r

    def __rand__(self, other):
        r = Calc(self, other)
        r.value = r.cq1val and r.cq2val
        return r

    def __abs__(self):
        r = Calc(self, None)
        r.value = r.cq1val
        return r
    
    def __call__(self, g:Graph):
        res = self.resolve(g)
        return res

def batched(iterable, n):
    "Batch data into tuples of length n. The last batch may be shorter."
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while batch := tuple(islice(it, n)):
        yield batch


@dataclass
class GraphCQ(CQ):
    """
    Instantiating a GraphCQ object: 
    (1) we create a SHACL shape that will be used for validation over a graph input 
    (2) we generate a SPARQL query that will support the retrieval of the uri if the shape is valid (using Gabe's shape-to-query component)
    """
    description: str = "GraphCQ"
    unit: UNIT.unit = field(init=False, repr=False)
    implementation: list = field(init=False, repr=False)

    def __init__(self, point: int, *patterns):
        """
        Gabe:
        I'm apologizing in advance for how wonky this implementation is, but here goes:

        Ignore the first item for now. The second argument is a list of nodes describing
        the node shape. The first argument of this list is *always* the targetClass of the shape.
        Every *pair* of arguments thereafter is a path/class pairing

        GraphCQ(<ignore>, [BRICK.AHU]) -> ":shape a sh:NodeShape ; sh:targetClass brick:AHU ;"
        GraphCQ(<ignore>, [BRICK.AHU, BRICK.hasPoint, BRICK.Sensor] -> ":shape a sh:NodeShape ; sh:targetClass BRICK:AHU ; 
                                                                        sh:property [ sh:path brick:hasPoint ; sh:qualifiedValueShape [ sh:class brick:Sensor ] ;
                                                                                      sh:qualifiedMinCount 1 ]"

        The first argument is the *index* of the *path/class* pair that corresponds to the point we want to extract as part of the resolution process.

        GraphCQ(0, [BRICK.AHU, BRICK.hasPoint, BRICK.Sensor]) -> will retrieve the "sensor" value
        GraphCQ(1, [BRICK.AHU, BRICK.hasPoint, BRICK.Sensor, BRICk.hasPoint, BRICK.Setpoint]) -> will retrieve the "setpoint" value
        """
        self.shape = Graph()
        self.query = ""
        self.description = '_'.join(x.fragment for sublist in patterns for x in sublist)
        shape = GCQ[self.description]
        self.shape.add((shape, A, SH.NodeShape))

        for pattern in patterns:
            if len(pattern) >= 1 and pattern[0]:
                self.shape.add((shape, SH.targetClass, pattern[0]))
            if len(pattern) >= 3:
                for idx, (prop, classname) in enumerate(batched(pattern[1:], 2)):
                    pshape = BNode()
                    tshape = BNode()
                    self.shape.add((shape, SH.property, pshape))
                    self.shape.add((pshape, SH.path, prop))
                    self.shape.add((pshape, SH.qualifiedValueShape, tshape))
                    self.shape.add((tshape, SH["class"], classname))
                    self.shape.add((pshape, SH.qualifiedMinCount, Literal(1)))
                    if idx == point:
                        self.shape.add((pshape, SH.name, Literal("point")))

    def join_candidates(self, g: Graph) -> List[Node]:
        """
        Generates a SPARQL query that retrieves the targetClass and the values on
        each of the sh:property associated with the targetClass. It assigns the 'target'
        variable to the targetClass and the 'point' variable to the property shape identified
        in the __init__ function above

        For example:

        GraphCQ(0, [BRICK.VAV, BRICK.hasPoint, BRICK.Supply_Air_Temperature_Sensor]),

        results in the shape:

        :long_autogenerated_name a sh:NodeShape ;
            sh:targetClass brick:VAV ;
            sh:property [
                sh:name "point" ;
                sh:path brick:hasPoint ;
                sh:qualifiedValueShape [ sh:class brick:Supply_Air_Temperature_Sensor ] ;
                sh:qualifiedMinCount 1 ;
            ] .

        results in this query

        SELECT ?target ?point WHERE {
            ?target rdf:type/rdfs:subClassOf* brick:VAV .
            ?target brick:hasPoint ?point .
            ?point a brick:Supply_Air_Temperature_Sensor .
        }
        """
        self.query = shape_to_query(self.shape, GCQ[self.description])
        res = g.query(self.query)
        self.query = res
        targets = set(row['target'] for row in res)
        return targets

    def qualify(self, graph: Graph) -> bool:
        """
        Returns true if the CQ can resolve on the given graph
        """
        result = pyshacl.validate(data_graph=graph, shacl_graph=self.shape)
        return result[0]

    def resolve(self, g: Graph, bindings) -> Node:
        self.query = shape_to_query(self.shape, GCQ[self.description])
        res = list(g.query(self.query, initBindings=bindings))
        row = res[0]
        # TODO: get an actual value?
        return row['point']

@dataclass
class Calc(CQ):
    """
    A class supporting calculations through python's magic methods. Calc objects are created automatically when we use the magic functions of the class CQ.
    
    The purpose of this implementation is to enable calculations between CQ objects as python does with numbers. For example: 
    if Tma and Tsa are CQ objects, we can write: 
    Tma + Tsa - 100 and retrieve:
    Tma.value + Tsa.value - 100 = <some number>

    where Tma.value, Tsa.value should (yet to implement) provide the actual value retrieved at a specific time for Tma.
    """
    description: str = field(init=False, repr=False)
    implementation: list = field(init=False)
    value: str = field(init=False)
    unit: UNIT = field(init=False, repr=False)
    cq1val: float = field(init=False)
    cq1val: float = field(init=False)
    cq1: CQ
    cq2: CQ

    def __post_init__(self):
        self.cq1val = np.NaN
        self.cq2val = np.NaN
        self.implementation = []
        self.value = np.NaN

        if isinstance(self.cq1, CQ) and isinstance(self.cq2, CQ):
            self.cq1val = self.cq1.value
            self.cq2val = self.cq2.value
        elif isinstance(self.cq1, float) and isinstance(self.cq2, CQ):
            self.cq1val = self.cq1
            self.cq2val = self.cq2.value
        elif isinstance(self.cq1, CQ) and isinstance(self.cq2, float):
            self.cq1val = self.cq1.value
            self.cq2val = self.cq2
        elif isinstance(self.cq1, int) and isinstance(self.cq2, CQ):
            self.cq1val = float(self.cq1)
            self.cq2val = self.cq2.value
        elif isinstance(self.cq1, CQ) and isinstance(self.cq2, int):
            self.cq1val = self.cq1.value
            self.cq2val = float(self.cq2)
        if not(isinstance(self.cq2, (Calc, float, int, type(None)))):
            self.implementation.append(self.cq2)
        if not(isinstance(self.cq1, (Calc, float, int, type(None)))):
            self.implementation.append(self.cq1)
        if isinstance(self.cq1, Calc):
            self.implementation.extend(self.cq1.implementation)
        if isinstance(self.cq2, Calc):
            self.implementation.extend(self.cq2.implementation)

@dataclass
class VirtualCQ(CQ):
    description: str = field(init=False, repr=False)
    unit: UNIT.unit = field(init=False, repr=False)
    implementation: list = field(init=False)
    value: float

    def __post_init__(self):
        self.implementation = self.value.implementation
        self.value = self.value.value

@dataclass
class DefaultCQ(CQ):
    description: str = field(init=False, repr=False)
    unit: UNIT.unit = field(init=False, repr=False)
    implementation: list = field(init=False)
    value: float

    def __post_init__(self):
        self.implementation = [self.value]



def get_cqs(fn: Callable) -> Dict:
    """
    Returns all the CQs used in the function
    """
    cqs = {}
    for param in inspect.signature(fn).parameters.values():
        if isinstance(param.default, CQ):
            cqs[param.name] = param.default
    return cqs

def is_applicable(g: Graph, fn: Callable) -> bool:
    cqs: Dict[str, CQ] = get_cqs(fn)
    for cq in cqs.values():
        if hasattr(cq, 'qualify') and not cq.qualify(g):
            return False
    return True

def resolve(g: Graph, fn: Callable) -> List[Callable]:
    """
    Given a graph and a function which uses CQs, generates
    a copy of the function w/ the CQs resolved to some values
    """
    cqs: Dict[str, CQ] = get_cqs(fn)

    # for each implementation, get all of the values of the 'target'
    # variable. This helps us join multiple CQ resolutions together
    candidates = defaultdict(list)
    for name, cq in cqs.items():
        for impl in cq.implementation:
            candidates[name].append(impl.join_candidates(g))

    # for a given target node (e.g. an AHU instance), gets the
    # best implementation for all CQs in the function. The "best"
    # implementation is the one that appears earliest in the implementation list
    def get_best_implementation(target: Node) -> Dict:
        best_impl = {}
        for name, candidate_list in candidates.items():
            for idx, candidate_impl in enumerate(candidate_list):
                if target in candidate_impl:
                    best_impl[name] = cqs[name].implementation[idx]
                    break
        return best_impl

    # figure out all possible targets
    all_targets = set()
    for candidate_list in candidates.values():
        for s in candidate_list:
            all_targets.update(s)

    resolved = []
    for target in all_targets:
        best_impl = get_best_implementation(target)
        if len(best_impl) != len(cqs):
            print(f"CANNOT RUN RULE ON {target}")
            continue
        impl = {k: v.resolve(g, {'target': target}) for k,v in best_impl.items()}
        resolved.append(partial(fn, g, **impl)) 

    return resolved

# %%
