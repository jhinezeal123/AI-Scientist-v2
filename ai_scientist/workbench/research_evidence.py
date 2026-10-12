"""Upstream citation and visual-review operations over collected run evidence."""
import json
from pathlib import Path
import re
from types import SimpleNamespace

from .research_literature import LiteratureSearch, saved_search_key


def citation_keys(text):
    return set(re.findall(r'@\w+\s*\{\s*([^,\s]+)\s*,', text))


def gather_citations(pipeline):
    from ai_scientist.perform_icbinb_writeup import get_citation_addition
    from .tree_search import write_json
    root = pipeline.root
    search = LiteratureSearch(root / 'citation-searches', pipeline.owner.check_running,
                              api_key=saved_search_key(pipeline.owner.service.store.workspace))
    bib = ''
    progress = []
    idea = (pipeline.owner.root / 'idea.md').read_text(encoding='utf-8')
    evidence = json.dumps({'stages': pipeline.owner.stage_results,
                          'seed_results': pipeline.seed_results}, ensure_ascii=False)
    for index in range(pipeline.plan.citation_rounds):
        pipeline.owner.check_running()
        addition, done = get_citation_addition(pipeline.client, pipeline.owner.service.config.codex_model,
            (evidence, bib), index, pipeline.plan.citation_rounds, idea, search=search)
        pipeline.owner.check_running()
        if addition:
            keys = citation_keys(addition)
            if not keys:
                raise ValueError('Citation round returned no bibliographic entry')
            # Upstream generates additions from the search API's BibTeX only.
            if not keys.intersection(citation_keys(bib)):
                bib += '\n' + addition
        progress.append({'round': index+1, 'done': done, 'keys': sorted(citation_keys(bib))})
        (root / 'references.bib').write_text(bib, encoding='utf-8')
        write_json(root / 'citations_progress.json', {'status':'running','rounds':progress,'searches':search.records})
        if done:
            break
    if not bib.strip() or not search.records:
        raise ValueError('Citation gathering chưa lấy được BibTeX từ Semantic Scholar; xem citation-searches')
    write_json(root / 'citations_progress.json', {'status':'completed','rounds':progress,'searches':search.records,
        'termination':'model_finished' if done else 'round_limit', 'keys':sorted(citation_keys(bib))})
    return ['research/references.bib','research/citations_progress.json']


def analyze_plots(owner, node, paths):
    """Run upstream's actual image analysis schema and prompt over collected images."""
    from ai_scientist.treesearch.parallel_agent import MinimalAgent
    from ai_scientist.treesearch.backend import use_query_provider
    from .research_images import validate_images
    from .tree_search import write_json
    paths = validate_images(paths)
    if not paths:
        node.plot_analyses = []
        node.vlm_feedback_summary = []
        node.is_buggy_plots = True
        raise ValueError('VLM chưa nhận được hình thí nghiệm; agent cần tạo PNG/JPEG trong output')
    # The upstream selector is bounded at ten; select collected paths only.
    node.plot_paths = [str(p) for p in paths[:10]]
    model = owner.service.config.codex_model
    role = SimpleNamespace(task_desc=(owner.root/'idea.md').read_text(encoding='utf-8'),
        cfg=SimpleNamespace(agent=SimpleNamespace(feedback=SimpleNamespace(model=model,temp=.3),
                                                  vlm_feedback=SimpleNamespace(model=model,temp=.3))),
        _determine_datasets_successfully_tested=lambda _: node.datasets_successfully_tested)
    previous = getattr(owner, 'agent_stage', None)
    owner.agent_stage = 'vision'
    try:
        with use_query_provider(owner.query):
            MinimalAgent._analyze_plots_with_vlm(role, node)
        write_json(Path(node.exp_dir) / 'vlm-review.json', {'images':node.plot_paths,
            'plot_analyses':node.plot_analyses,'valid_plots_received':not node.is_buggy_plots,
            'vlm_feedback_summary':node.vlm_feedback_summary,
            'omitted_images':len(paths)-len(node.plot_paths)})
    finally:
        owner.agent_stage = previous


def review_pdf(pipeline, *, selection=False, reflection=0):
    from ai_scientist.perform_vlm_review import (perform_imgs_cap_ref_review,
        detect_duplicate_figures, perform_imgs_cap_ref_review_selection)
    from .tree_search import write_json
    pdf = pipeline.root / 'paper.pdf'
    if not pdf.is_file():
        raise ValueError('VLM PDF review requires a compiled paper')
    previous = getattr(pipeline.owner,'agent_stage',None)
    pipeline.owner.agent_stage = 'vision'
    try:
        reviews = perform_imgs_cap_ref_review(pipeline.client, pipeline.owner.service.config.codex_model, str(pdf))
        if not reviews or any(not isinstance(v,dict) or not v for v in reviews.values()):
            raise ValueError('VLM chưa trả review hợp lệ cho các hình trong PDF')
        duplicates = detect_duplicate_figures(pipeline.client, pipeline.owner.service.config.codex_model,str(pdf))
        if not isinstance(duplicates,str) or not duplicates.strip():
            raise ValueError('VLM duplicate-figure review failed')
        result = {'figures':reviews, 'duplicates':duplicates}
        if selection:
            import pymupdf
            with pymupdf.open(pdf) as document:
                page_info = f'{len(document)} pages; reflection {reflection}; preserve the selected publication page limit.'
            chosen = perform_imgs_cap_ref_review_selection(pipeline.client, pipeline.owner.service.config.codex_model,
                                                          str(pdf), page_info)
            if not chosen or any(not isinstance(v,dict) or not v for v in chosen.values()):
                raise ValueError('VLM figure-selection review failed')
            result['selection'] = chosen
        path = pipeline.root / (f'vlm-reflection-{reflection}.json' if selection else 'vlm-paper-review.json')
        write_json(path, result)
        return result
    finally:
        pipeline.owner.agent_stage = previous
