import random
from collections import defaultdict
import string
from rdflib import Graph, URIRef, Namespace
from rdflib.paths import ZeroOrMore, ZeroOrOne
from rdflib.term import Node
from typing import Tuple, List, Dict

BRICK = Namespace("https://brickschema.org/schema/Brick#")
APAR = Namespace("http://openmetrics.eu/openmetrics/apar#")
OM = Namespace("http://openmetrics.eu/openmetrics#")
SH = Namespace("http://www.w3.org/ns/shacl#")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
GCQ = Namespace("https://brickschema.org/schema/Brick/GraphCQ#")
UNIT = Namespace("http://qudt.org/vocab/unit#")
QUDT = Namespace("https://qudt.org/2.1/schema/datatype")
A = RDF.type

def shape_to_query(graph: Graph, shape: URIRef) -> str:
        """
        This method takes a URI representing a SHACL shape as an argument and returns
        a SPARQL query selecting the information which would be used to satisfy that
        SHACL shape. This uses the following rules:
        - `<shape> sh:targetClass <class>` -> `?target rdf:type/rdfs:subClassOf* <class>`
        - `<shape> sh:property [ sh:path <path>; sh:class <class>; sh:name <name> ]` ->
            ?target <path> ?name . ?name rdf:type/rdfs:subClassOf* <class>
        """
        clauses, project = _shape_to_where(graph, shape)
        preamble = """PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        """
        return f"{preamble} SELECT {' '.join(project)} WHERE {{\n{clauses}\n}}"

def _shape_to_where(graph: Graph, shape: URIRef) -> Tuple[str, List[str]]:
    # we will build the query as a string
    clauses: str = ""
    # build up the SELECT clause as a set of vars
    project: Set[str] = {"?target"}

    # local state for generating unique variable names
    prefix = "".join(random.choice(string.ascii_lowercase) for _ in range(2))
    variable_counter = 0

    def gensym():
        nonlocal variable_counter
        varname = f"{prefix}{variable_counter}"
        variable_counter += 1
        return varname

    # `<shape> sh:targetClass <class>` -> `?target rdf:type/rdfs:subClassOf* <class>`
    targetClasses = graph.objects(shape, SH.targetClass | SH["class"])
    tc_clauses = [
        f"?target rdf:type/rdfs:subClassOf* {tc.n3()} .\n" for tc in targetClasses  # type: ignore
    ]
    clauses += " UNION ".join(tc_clauses)

    # find all of the non-qualified property shapes. All of these will use the same variable
    # for all uses of the same sh:path value
    pshapes_by_path: Dict[Node, List[Node]] = defaultdict(list)
    for pshape in graph.objects(shape, SH.property):
        path = graph.value(pshape, SH.path)
        if not graph.value(pshape, SH.qualifiedValueShape):
            pshapes_by_path[path].append(pshape)  # type: ignore

    for dep_shape in graph.objects(shape, SH.node):
        dep_clause, dep_project = _shape_to_where(graph, dep_shape)
        clauses += dep_clause
        project.update(dep_project)

    for or_clause in graph.objects(shape, SH["or"]):
        items = list(graph.objects(or_clause, (RDF.rest * ZeroOrMore) / RDF.first))  # type: ignore
        or_parts = []
        for item in items:
            or_body, or_project = _shape_to_where(graph, item)
            or_parts.append(or_body)
            project.update(or_project)
        clauses += " UNION ".join(f"{{ {or_body} }}" for or_body in or_parts)

    # assign a unique variable for each sh:path w/o a qualified shape
    pshape_vars: Dict[Node, str] = {}
    for pshape_list in pshapes_by_path.values():
        varname = f"?{gensym()}"
        for pshape in pshape_list:
            pshape_vars[pshape] = varname

    for pshape in graph.objects(shape, SH.property):
        # get the varname if we've already assigned one for this pshape above,
        # or generate a new one. When generating a name, use the SH.name field
        # in the PropertyShape or generate a unique one
        name = pshape_vars.get(
            pshape, f"?{graph.value(pshape, SH.name) or gensym()}".replace(" ", "_")
        )
        path = graph.value(pshape, SH.path)
        qMinCount = graph.value(pshape, SH.qualifiedMinCount) or 0

        pclass = graph.value(
            pshape, (SH["qualifiedValueShape"] * ZeroOrOne / SH["class"])  # type: ignore
        )
        if pclass:
            clause = f"?target {path.n3()} {name} .\n {name} rdf:type/rdfs:subClassOf* {pclass.n3()} .\n"
            if qMinCount == 0:
                clause = f"OPTIONAL {{ {clause} }} .\n"
            clauses += clause
            project.add(name)

        pnode = graph.value(
            pshape, (SH["qualifiedValueShape"] * ZeroOrOne / SH["node"])  # type: ignore
        )
        if pnode:
            node_clauses, node_project = _shape_to_where(graph, pnode)
            clause = f"?target {path.n3()} {name} .\n"
            clause += node_clauses.replace("?target", name)
            if qMinCount == 0:
                clause = f"OPTIONAL {{ {clause} }}"
            clauses += clause
            project.update({p.replace("?target", name) for p in node_project})

        pvalue = graph.value(pshape, SH.hasValue)
        if pvalue:
            clauses += f"?target {path.n3()} {pvalue.n3()} .\n"

    return clauses, list(project)
