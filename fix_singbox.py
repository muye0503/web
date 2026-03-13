#!/usr/bin/env python3
"""Fix sing-box config for 1.13.2 compatibility.
Usage: python3 fix_singbox.py input.json output.json
"""
import json, sys

src, dst = sys.argv[1], sys.argv[2]
with open(src) as f:
    cfg = json.load(f)

# 1. Inbounds: remove sniff fields, fix tun inet4_address -> address
has_sniff = False
for ib in cfg.get('inbounds', []):
    if ib.pop('sniff', None):
        has_sniff = True
    ib.pop('sniff_timeout', None)
    ib.pop('domain_strategy', None)
    if ib.get('type') == 'tun':
        for old in ('inet4_address', 'inet6_address'):
            if old in ib:
                val = ib.pop(old)
                lst = ib.setdefault('address', [])
                (lst.extend if isinstance(val, list) else lst.append)(val)

# 2. Remove deprecated block/dns special outbounds
cfg['outbounds'] = [o for o in cfg['outbounds'] if o.get('type') not in ('block', 'dns')]

# 3. Route rules: dns-out -> hijack-dns, geoip:cn -> rule_set, add sniff
new_route_rules = []
if has_sniff:
    new_route_rules.append({"action": "sniff"})
for rule in cfg['route']['rules']:
    if rule.get('outbound') == 'dns-out' and rule.get('protocol') == 'dns':
        new_route_rules.append({"protocol": "dns", "action": "hijack-dns"})
    elif rule.get('geoip') == 'cn':
        r = {k: v for k, v in rule.items() if k != 'geoip'}
        r['rule_set'] = ['geoip-cn']
        new_route_rules.append(r)
    else:
        new_route_rules.append(rule)
cfg['route']['rules'] = new_route_rules
cfg['route']['default_domain_resolver'] = 'dns_resolver'

# 4. DNS rules: geosite -> rule_set, dns_block server -> action:reject
new_dns_rules = []
for rule in cfg['dns']['rules']:
    if 'outbound' in rule:  # deprecated outbound dns rule item, drop it
        continue
    if 'geosite' in rule:
        r = {k: v for k, v in rule.items() if k != 'geosite'}
        r['rule_set'] = [f'geosite-{g}' for g in rule['geosite']]
        if r.get('server') == 'dns_block':
            r.pop('server'); r.pop('disable_cache', None); r['action'] = 'reject'
        new_dns_rules.append(r)
    else:
        new_dns_rules.append(rule)
cfg['dns']['rules'] = new_dns_rules

# 5. DNS servers: old address format -> new typed format
#    address_resolver -> domain_resolver, http3 -> h3
def migrate_server(s):
    addr = s.get('address', '')
    tag = s.get('tag', '')
    base = {'tag': tag}
    # detour is not supported in new DNS server format (uses dialer, not outbound tag)
    if s.get('address_resolver'): base['domain_resolver'] = s['address_resolver']

    if addr == 'fakeip':              return {'type': 'fakeip', 'tag': tag}
    if addr.startswith('rcode://'):   return None  # removed, use action:reject in dns rules instead
    if addr.startswith('tls://'):     return {**base, 'type': 'tls',   'server': addr[len('tls://'):]}
    if addr.startswith('h3://'):
        hp = addr[len('h3://'):]
        sl = hp.find('/')
        h3 = {**base, 'type': 'h3', 'server': hp[:sl] if sl != -1 else hp}
        if sl != -1: h3['path'] = hp[sl:]
        return h3
    if addr.startswith('https://'):   return {**base, 'type': 'https', 'server_url': addr}
    return {**base, 'type': 'udp', 'server': addr}

cfg['dns']['servers'] = [s for s in (migrate_server(x) for x in cfg['dns']['servers']) if s]

# fix dns rules referencing removed rcode/block server
for rule in cfg['dns']['rules']:
    if rule.get('server') == 'block':
        rule.pop('server'); rule['action'] = 'reject'

# 5b. Move dns.fakeip range config into the fakeip server entry, remove top-level dns.fakeip
fakeip_cfg = cfg['dns'].pop('fakeip', {})
for s in cfg['dns']['servers']:
    if s.get('type') == 'fakeip':
        if fakeip_cfg.get('inet4_range'): s['inet4_range'] = fakeip_cfg['inet4_range']
        if fakeip_cfg.get('inet6_range'): s['inet6_range'] = fakeip_cfg['inet6_range']
        break

# 6. rule_set entries for geoip/geosite
used = set()
for rule in cfg['route']['rules']: used.update(rule.get('rule_set', []))
for rule in cfg['dns']['rules']:   used.update(rule.get('rule_set', []))

cfg['route']['rule_set'] = []
for rs in sorted(used):
    repo = 'sing-geoip' if rs.startswith('geoip-') else 'sing-geosite'
    cfg['route']['rule_set'].append({
        "tag": rs, "type": "remote", "format": "binary",
        "url": f"https://raw.githubusercontent.com/SagerNet/{repo}/rule-set/{rs}.srs",
        "download_detour": "🔰 节点选择"
    })

with open(dst, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print(f"Written to {dst}")
