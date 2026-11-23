"""Passive identity decoding, fixed UpdateScript_500.dll 1.35.20.001.
Evidence: MNKGAOHNBGO parser 0601CD83, login parser 060110F7,
roster parsers 0601B524/0601BF43, routing 0600654A/0600651A.
No text scanning, inferred names, or id2-as-UID fallback.
"""

class IdentityError(ValueError):
    pass

def fields(data):
    data = memoryview(data)
    pos = 0
    count = 0
    def varint():
        nonlocal pos
        out = 0
        for shift in range(0, 70, 7):
            if pos >= len(data):
                raise IdentityError('truncated identity varint')
            b = data[pos]
            pos += 1
            if shift == 63 and b > 1:
                raise IdentityError('identity uint64 overflow')
            out |= (b & 127) << shift
            if b < 128:
                return out
        raise IdentityError('overlong identity varint')
    while pos < len(data):
        count += 1
        if count > 100000:
            raise IdentityError('identity field limit')
        tag = varint()
        number, wire = tag >> 3, tag & 7
        if not number:
            raise IdentityError('zero identity field')
        if wire == 0:
            value = varint()
        else:
            size = varint() if wire == 2 else 8 if wire == 1 else 4 if wire == 5 else -1
            if size < 0 or size > len(data) - pos:
                raise IdentityError('invalid identity field length/wire')
            value = data[pos:pos + size]
            pos += size
        yield number, wire, value

def player(data):
    out = {}
    for number, wire, value in fields(data):
        if number == 1 and wire == 0:
            if value > 0xffffffff:
                raise IdentityError('player entity id exceeds uint32')
            out['entity_id'] = value
        elif number == 2 and wire == 0:
            out['uid'] = str(value)
        elif number == 3 and wire == 2:
            out['name'] = bytes(value).decode('utf-8', errors='strict')
    # An instance id is mandatory: never match a nickname or a prefab id.
    return out if out.get('entity_id') else None

def roster(data):
    result = []
    for number, wire, value in fields(data):
        if number == 1 and wire == 2:
            item = player(value)
            if item is not None:
                result.append(item)
    return result

def decode_identity(command, data):
    if command not in (1, 3, 6, 2005):
        return None
    event = {'command': command, 'players': [], 'removed': [], 'reset': command == 1}
    if command == 1:
        for number, wire, value in fields(data):
            if number == 2 and wire == 0:
                event['local_uid'] = str(value)
            elif number == 3 and wire == 0:
                event['local_entity_id'] = value
            elif number == 5 and wire == 2:
                event['players'].extend(roster(value))
    elif command == 3:
        event['players'] = roster(data)
    elif command == 6:
        event['players'] = roster(data)
        for number, wire, value in fields(data):
            if number == 2 and wire == 0:
                event['removed'].append(value)
            elif number == 2 and wire == 2:
                # FAPEPPHALFC parser accepts packed and unpacked uint32 IDs.
                block = memoryview(value)
                pos = 0
                while pos < len(block):
                    number_value = 0
                    for shift in range(0, 70, 7):
                        if pos >= len(block):
                            raise IdentityError('truncated removal id')
                        byte = block[pos]
                        pos += 1
                        if shift == 63 and byte > 1:
                            raise IdentityError('removal id overflow')
                        number_value |= (byte & 127) << shift
                        if byte < 128:
                            break
                    else:
                        raise IdentityError('overlong removal id')
                    if number_value > 0xffffffff:
                        raise IdentityError('removal id exceeds uint32')
                    event['removed'].append(number_value)
    else:
        for number, wire, value in fields(data):
            if number == 1 and wire == 0:
                event['local_uid'] = str(value)
    return event
