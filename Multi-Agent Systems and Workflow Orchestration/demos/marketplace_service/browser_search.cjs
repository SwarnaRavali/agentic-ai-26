const {chromium}=require('../runtime/browser/node_modules/playwright');
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const request=process.argv[2]||'black running shoes under 1000';
const bm=request.replaceAll(',','').match(/(?:under|below|budget|up to)\s*(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(k)?/i);
const limit=bm?Number(bm[1])*(bm[2]?1000:1):1000;
const query='black running shoes under '+limit;
const sites=[{name:'Amazon',host:'amazon.in',url:'https://www.amazon.in/s?k='+encodeURIComponent(query)},{name:'Flipkart',host:'flipkart.com',url:'https://www.flipkart.com/search?q='+encodeURIComponent(query)},{name:'Myntra',host:'myntra.com',url:'https://www.myntra.com/black-running-shoes?sort=price_asc'}];
(async()=>{
 const start=Date.now();const browser=await chromium.launch({channel:'chrome',headless:process.env.MARKETPLACE_BROWSER_HEADLESS==='1'});const context=await browser.newContext({locale:'en-IN',viewport:{width:1400,height:900}});const candidates=[],sources=[];
 try{for(const site of sites){
  const page=await context.newPage();let status='NO_EXTRACTABLE_CANDIDATES',observed_at=new Date().toISOString(),items=[],title='',error='';
  try{
   await page.goto(site.url,{waitUntil:'domcontentloaded',timeout:22000});await page.waitForTimeout(1800);title=await page.title();
   items=await page.evaluate((market)=>{
    const price=(t)=>{const m=t.match(/(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)/i);return m?Number(m[1].replaceAll(',','')):null;};
    let arr=[];
    if(market==='Amazon')for(const el of document.querySelectorAll('[data-component-type="s-search-result"]')){
     const a=el.querySelector('a:has(h2),h2 a,a.a-link-normal.s-no-outline'),h=el.querySelector('h2'),pr=el.querySelector('.a-price .a-offscreen');
     if(a&&h&&pr)arr.push({product_name:[...el.querySelectorAll('h2')].map(e=>e.innerText.trim()).join(' '),source_url:a.href,observed_price_inr:price(pr.innerText),source_excerpt:el.innerText.slice(0,1100)});
    }
    if(market==='Flipkart')for(const a of document.querySelectorAll('a[href*="/p/"]')){
     let el=a;for(let i=0;i<3&&el.parentElement;i++){if(price(el.innerText)&&el.innerText.length>60)break;el=el.parentElement;}
     const v=price(el.innerText);if(v&&a.href)arr.push({product_name:(a.title||a.innerText||el.innerText).slice(0,220),source_url:a.href,observed_price_inr:v,source_excerpt:el.innerText.slice(0,1100)});
    }
    if(market==='Myntra')for(const el of document.querySelectorAll('li.product-base')){
     const a=el.querySelector('a'),pr=el.querySelector('.product-discountedPrice,.product-price');const pm=pr?.innerText.match(/(?:Rs\.?|₹)\s*([\d,]+(?:\.\d{1,2})?)/i);const v=pm?Number(pm[1].replaceAll(',','')):null;
     if(a&&v)arr.push({product_name:[...el.querySelectorAll('h3,h4')].map(e=>e.innerText).join(' '),source_url:a.href,observed_price_inr:v,source_excerpt:el.innerText.slice(0,1100)});
    }
    return arr;
   },site.name);
   if(/captcha|robot|access denied|maintenance/i.test((await page.locator('body').innerText()).slice(0,2500)))status='BLOCKED_OR_UNAVAILABLE';
   if(items.length)status='OK';
   if(!items.length){
    const fallback='https://www.bing.com/search?q='+encodeURIComponent('site:'+site.host+' '+query+' price');
    await page.goto(fallback,{waitUntil:'domcontentloaded',timeout:18000});await page.waitForTimeout(1300);
    const rows=await page.locator('li.b_algo').evaluateAll(els=>els.map(el=>({product_name:el.querySelector('h2')?.innerText||'',source_url:el.querySelector('h2 a')?.href||'',source_excerpt:el.innerText.slice(0,1100)})));
    for(const row of rows){try{const u=new URL(row.source_url);const m=row.source_excerpt.match(/(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)/i);if((u.hostname===site.host||u.hostname.endsWith('.'+site.host))&&m)items.push({...row,observed_price_inr:Number(m[1].replaceAll(',','')),evidence_mode:'search_index_fallback'});}catch{}}
    if(items.length)status='SEARCH_INDEX_FALLBACK';
   }
   await page.screenshot({path:path.join(__dirname,'..','runs',site.name.toLowerCase()+'-latest.png'),fullPage:false});
  }catch(e){error=e.name;status='SOURCE_ERROR';}
  for(const item of items){try{let u=new URL(item.source_url);if(site.name==='Amazon'&&u.pathname==='/sspa/click'&&u.searchParams.get('url'))u=new URL(u.searchParams.get('url'),u.origin);if(site.name==='Amazon'){const m=u.pathname.match(/\/dp\/([A-Z0-9]{10})/);if(m)u=new URL('/dp/'+m[1],u.origin);}item.source_url=u.href;}catch{}}
  const seen=new Set();const good=items.filter(x=>{if(!x.source_url||!Number.isFinite(x.observed_price_inr)||x.observed_price_inr<=0||seen.has(x.source_url))return false;try{const h=new URL(x.source_url).hostname;if(h!==site.host&&!h.endsWith('.'+site.host))return false;}catch{return false;}seen.add(x.source_url);return true;}).slice(0,4);
  // Open up to two in-budget product pages per source to verify product attributes.
  for(const item of good.filter(o=>o.observed_price_inr<limit).slice(0,2)){
   const detail=await context.newPage();item.detail_status='UNAVAILABLE';
   try{
    await detail.goto(item.source_url,{waitUntil:'domcontentloaded',timeout:12000});await detail.waitForTimeout(1000);
    const final=new URL(detail.url());if(final.hostname!==site.host&&!final.hostname.endsWith('.'+site.host))throw Error('Source redirect outside allowlist');
    const data=await detail.evaluate(market=>{
      const txt=sel=>[...document.querySelectorAll(sel)].map(e=>e.innerText.trim()).filter(Boolean).join('\n');
      if(market==='Amazon')return {name:txt('#productTitle'),details:txt('#variation_color_name .selection, #productDetails_techSpec_section_1, #productDetails_detailBullets_sections1, #productOverview_feature_div, #detailBullets_feature_div, #feature-bullets'),priceText:txt('#corePriceDisplay_desktop_feature_div .a-price .a-offscreen, #corePrice_feature_div .a-price .a-offscreen')};
      if(market==='Flipkart')return {name:txt('h1'),details:txt('table').slice(0,7000),priceText:''};
      return {name:txt('.pdp-title, .pdp-name'),details:txt('.pdp-product-description-content, .index-tableContainer').slice(0,7000),priceText:txt('.pdp-price strong')};
    },site.name);
    if(data.name){item.product_name=data.name;item.source_url=detail.url();item.source_excerpt+='\nPRODUCT PAGE: '+data.name+'\n'+data.details;item.source_excerpt=item.source_excerpt.slice(0,8000);item.observed_at=new Date().toISOString();item.detail_status='OBSERVED';
     const price=data.priceText.match(/(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)/i);if(price)item.observed_price_inr=Number(price[1].replaceAll(',',''));
     await detail.screenshot({path:path.join(__dirname,'..','runs',site.name.toLowerCase()+'-product-latest.png'),fullPage:false});
    }
   }catch(e){item.detail_status='ERROR_'+e.name;}finally{await detail.close();}
  }
  for(const x of good)candidates.push({...x,offer_id:site.name.slice(0,3).toUpperCase()+'-'+crypto.createHash('sha256').update(x.source_url).digest('hex').slice(0,10),marketplace:site.name,observed_at:x.observed_at||observed_at,evidence_mode:x.evidence_mode||'retailer_page',unverified_fields:['size','stock','delivery','returns','shipping','checkout_total']});
  sources.push({marketplace:site.name,search_url:site.url,title,observed_at,status,candidate_count:good.length,error:error||null});await page.close();
 }}finally{await browser.close();}
 process.stdout.write(JSON.stringify({mode:'live_browser',search_provider:'Playwright + system Chrome',request,observed_at:new Date().toISOString(),candidates,sources,limitations:['Observed item prices are not verified checkout totals.','Search-index fallback is labeled explicitly.','Missing required evidence cannot be invented.'],visible_browser:process.env.MARKETPLACE_BROWSER_HEADLESS!=='1',duration_ms:Date.now()-start}));
})().catch(e=>{process.stderr.write(e.stack);process.exit(1)});
