"""Read a bounded window of display lines without transferring the entire log."""

# A trailing newline terminates a line; an empty record still occupies one line.
LINE_COUNT = "MAX(1, length(text)-length(replace(text,char(10),'')) + (substr(text,-1,1)!=char(10)))"


def read_log_window(store, project_id, run_id, generation, offset=0, limit=80,
                    requested_generation=None):
    if offset < 0 or not 0 <= limit <= 200 or (requested_generation is not None and requested_generation < 1):
        raise ValueError('Invalid log window or generation')
    store.run(project_id, run_id)
    reset = requested_generation is not None and requested_generation != generation
    if reset:
        offset = 0
    with store.connection(project_id) as connection:
        total = connection.execute(f'''SELECT COUNT(*) AS records, COALESCE(SUM({LINE_COUNT}),0) AS lines
            FROM logs WHERE run_id=? AND generation=?''', (run_id, generation)).fetchone()
        offset = min(offset, total['lines'])
        rows = []
        if limit:
            rows = connection.execute(f'''WITH measured AS (
                SELECT seq,text,stream,{LINE_COUNT} AS line_count FROM logs WHERE run_id=? AND generation=?
            ), positioned AS (
                SELECT *, COALESCE(SUM(line_count) OVER (ORDER BY seq ROWS BETWEEN UNBOUNDED PRECEDING
                    AND 1 PRECEDING),0) AS line_start FROM measured
            ) SELECT * FROM positioned WHERE line_start < ? AND line_start+line_count > ? ORDER BY seq''',
                (run_id, generation, offset + limit, offset)).fetchall()
    lines = []
    for row in rows:
        parts = row['text'].split('\n')
        if row['text'].endswith('\n'):
            parts.pop()
        for index in range(max(0, offset - row['line_start']), min(len(parts), offset + limit - row['line_start'])):
            lines.append({'index': row['line_start'] + index, 'seq': row['seq'],
                          'text': parts[index].removesuffix('\r'), 'stream': row['stream']})
    return {'generation': generation, 'total_records': total['records'], 'total_lines': total['lines'],
            'offset': offset, 'lines': lines, 'reset': reset}
