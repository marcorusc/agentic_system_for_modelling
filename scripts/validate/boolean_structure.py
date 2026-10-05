"""Bounded exact Boolean artifact analysis, without eval, imports or simulation."""
from __future__ import annotations
from collections import deque
from pathlib import Path
import re

TOKEN = re.compile(r'\s*([A-Za-z_][A-Za-z0-9_]*|[01!&|()])')


class LimitExceeded(ValueError):
    pass


class Expression:
    def __init__(self, expression: str, nodes: list[str]):
        if len(expression) > 10000:
            raise ValueError('Boolean expression exceeds length bound')
        self.tokens = []
        offset = 0
        expression = expression.strip()
        while offset < len(expression):
            match = TOKEN.match(expression, offset)
            if match is None:
                raise ValueError(f'unsupported Boolean token at position {offset}')
            self.tokens.append(match[1]); offset = match.end()
        self.index = 0
        self.nodes = {node: i for i, node in enumerate(nodes)}
        if not self.tokens or len(self.tokens) > 500:
            raise ValueError('empty or excessive Boolean expression')
        self.tree = self.parse_or()
        if self.index != len(self.tokens):
            raise ValueError('unexpected trailing Boolean tokens')

    def take(self, token):
        if self.index < len(self.tokens) and self.tokens[self.index] == token:
            self.index += 1
            return True
        return False

    def parse_or(self):
        value = self.parse_and()
        while self.take('|'):
            value = ('or', value, self.parse_and())
        return value

    def parse_and(self):
        value = self.parse_atom()
        while self.take('&'):
            value = ('and', value, self.parse_atom())
        return value

    def parse_atom(self):
        if self.take('!'):
            return ('not', self.parse_atom())
        if self.take('('):
            result = self.parse_or()
            if not self.take(')'):
                raise ValueError('missing closing parenthesis')
            return result
        if self.index >= len(self.tokens):
            raise ValueError('missing Boolean operand')
        token = self.tokens[self.index]; self.index += 1
        if token in ('0', '1'):
            return ('const', token == '1')
        if token not in self.nodes:
            raise ValueError(f'unknown regulator: {token}')
        return ('node', self.nodes[token])

    def __call__(self, state: int):
        def visit(tree):
            op = tree[0]
            if op == 'node': return bool(state & (1 << tree[1]))
            if op == 'const': return tree[1]
            if op == 'not': return not visit(tree[1])
            if op == 'and': return visit(tree[1]) and visit(tree[2])
            return visit(tree[1]) or visit(tree[2])
        return visit(self.tree)


def load_bnet(path: Path):
    rules = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or line.lower().replace(' ', '') == 'targets,factors':
            continue
        if ',' not in line:
            raise ValueError('BNET row requires target, expression')
        node, rule = [v.strip() for v in line.split(',', 1)]
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', node) or node in rules:
            raise ValueError('BNET target must be a unique identifier')
        rules[node] = rule
    nodes = sorted(rules)
    if not nodes or len(nodes) > 20:
        raise ValueError('exact analysis supports 1..20 nodes')
    return nodes, [Expression(rules[node], nodes) for node in nodes]


def terminal_scc(graph):
    visited, order = set(), []
    for start in graph:
        if start in visited: continue
        stack = [(start, False)]
        while stack:
            node, done = stack.pop()
            if done:
                order.append(node); continue
            if node in visited: continue
            visited.add(node); stack.append((node, True))
            stack.extend((v, False) for v in graph[node] if v not in visited)
    reverse = {node: [] for node in graph}
    for node, children in graph.items():
        for child in children: reverse[child].append(node)
    assigned, components = set(), []
    for start in reversed(order):
        if start in assigned: continue
        stack, component = [start], set()
        while stack:
            node = stack.pop()
            if node in assigned: continue
            assigned.add(node); component.add(node)
            stack.extend(reverse[node])
        components.append(component)
    return [part for part in components if all(child in part for node in part for child in graph[node])]


def analyze(path: Path, options: dict):
    nodes, functions = load_bnet(path)
    limit = options['max_states']
    if type(limit) is not int or not 1 <= limit <= 1000000:
        raise ValueError('max_states must be an integer in [1,1000000]')
    mode = options['analysis']
    if mode in ('fixed_points', 'readout_exclusivity'):
        if 2**len(nodes) > limit:
            raise LimitExceeded('complete state space exceeds max_states')
        if mode == 'fixed_points':
            fixed = [[node for i, node in enumerate(nodes) if state & (1 << i)] for state in range(2**len(nodes))
                     if all(fn(state) == bool(state & (1 << i)) for i, fn in enumerate(functions))]
            expected = options['expected_count']
            if type(expected) is not int or expected < 0:
                raise ValueError('expected_count must be a nonnegative integer')
            return len(fixed) == expected, {'fixed_points': fixed, 'states_checked': 2**len(nodes)}
        outputs = options['readout_nodes']
        if len(outputs) < 2 or len(set(outputs)) != len(outputs) or any(n not in nodes for n in outputs):
            raise ValueError('readout_nodes requires at least two distinct known outputs')
        indices = [nodes.index(n) for n in outputs]
        for state in range(2**len(nodes)):
            active = [nodes[i] for i in indices if functions[i](state)]
            if len(active) > 1:
                return False, {'counterexample_state': [n for i, n in enumerate(nodes) if state & (1 << i)], 'simultaneously_enabled_rules': active}
        return True, {'states_checked': 2**len(nodes), 'semantics': 'mutual exclusivity of evaluated readout functions, not asynchronous node values'}
    if mode != 'reachable_attractors':
        raise ValueError('unknown structural analysis')
    initial = options['initial_state']
    if not isinstance(initial, dict) or set(initial) != set(nodes) or any(type(v) is not bool for v in initial.values()):
        raise ValueError('initial_state must explicitly assign every node a Boolean')
    start = sum(1 << i for i, node in enumerate(nodes) if initial[node])
    queue, seen, graph, edges = deque([start]), {start}, {}, 0
    while queue:
        state = queue.popleft()
        children = [state ^ (1 << i) for i, fn in enumerate(functions) if fn(state) != bool(state & (1 << i))]
        graph[state] = children; edges += len(children)
        if edges > 2000000:
            raise LimitExceeded('asynchronous graph exceeds 2000000-edge bound')
        for child in children:
            if child not in seen:
                seen.add(child)
                if len(seen) > limit:
                    raise LimitExceeded('reachable states exceed max_states')
                queue.append(child)
    terminal = terminal_scc(graph)
    summaries = [{'size': len(part), 'fixed_on': [n for i, n in enumerate(nodes) if all(s & (1 << i) for s in part)],
                  'fixed_off': [n for i, n in enumerate(nodes) if all(not s & (1 << i) for s in part)]} for part in terminal]
    expected = options['expected_count']
    if type(expected) is not int or expected < 1:
        raise ValueError('expected_count must be a positive integer')
    return len(terminal) == expected, {'reachable_states': len(seen), 'terminal_sccs': summaries, 'semantics': 'general asynchronous single-node updates'}
