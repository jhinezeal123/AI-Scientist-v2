import {readFileSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {execFileSync} from 'node:child_process';
import postcss from 'postcss';

const base=resolve('src/vendor/t3code'), temporary=mkdtempSync(join(tmpdir(),'workbench-t3-css-'));
try{
  const generated=join(temporary,'utilities.css');
  execFileSync(process.execPath,['node_modules/@tailwindcss/cli/dist/index.mjs','-i',join(base,'t3.input.css'),'-o',generated,'--minify'],{stdio:'inherit'});
  const css=postcss.parse(readFileSync(generated,'utf8'));
  // The host uses unlayered CSS. Keep T3's cascade intact inside its own scope.
  css.walkAtRules('layer',rule=>{if(rule.nodes)rule.replaceWith(...rule.nodes);else rule.remove();});
  css.walkRules(rule=>{
    if(rule.parent.type==='atrule' && /keyframes$/.test(rule.parent.name))return;
    rule.selector=postcss.list.comma(rule.selector).flatMap(selector=>{
      if(selector===':root'||selector===':host'||selector==='html'||selector==='body')return [':scope'];
      if(selector.startsWith(':scope'))return [selector];
      // Give both the reset and utilities the same scope specificity; host styles
      // cannot override T3 controls. Include the scope root for utility classes.
      return [`:scope:is(${selector})`,`:scope ${selector}`];
    }).join(',');
  });
  const scope=postcss.atRule({name:'scope',params:'(.t3-preset-ui)'});
  for(const node of [...css.nodes])if(node.type!=='atrule'||!['property','keyframes','charset'].includes(node.name))scope.append(node);
  css.append(scope);
  writeFileSync(join(base,'t3.css'),css.toString());
}finally{
  if(!temporary.startsWith(join(tmpdir(),'workbench-t3-css-')))throw new Error('Unexpected CSS temporary path');
  rmSync(temporary,{recursive:true,force:true});
}
