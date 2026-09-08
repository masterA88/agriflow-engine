
-- Demo seed: 220 synthetic visitors over 39 days (2026-08-01 to 2026-09-08). Tagged app_version='demo-seed' and
-- detail.source='demo' so they can be purged with one DELETE and never confused with real rows.
DO $$
DECLARE
  kabs TEXT[]; pops BIGINT[]; totpop BIGINT := 0;
  comms TEXT[] := ARRAY['cabai_rawit','bawang_merah','beras_medium','beras_premium','bawang_putih','cabai_merah','daging_ayam','telur_ayam'];
  cw   NUMERIC[] := ARRAY[0.28,0.22,0.15,0.10,0.10,0.08,0.04,0.03];
  tabs TEXT[] := ARRAY['beranda','peta','distribusi','simulasi','harga','laporan','bantuan','notifikasi'];
  tw   NUMERIC[] := ARRAY[0.22,0.20,0.20,0.10,0.15,0.06,0.04,0.03];
  presets TEXT[] := ARRAY['semeru','ramadan','bbm','banjir','suramadu','ramadan,bbm','semeru,banjir'];
  labels TEXT[] := ARRAY['Beranda','Peta Pasokan','Rekomendasi Distribusi','Simulasi What-if','Harga & Prakiraan','Laporan & KPI','Bantuan','Notifikasi'];
  p INT; d INT; day DATE; base TIMESTAMPTZ; t TIMESTAMPTZ; tok TEXT; sid UUID; signed BOOLEAN;
  home TEXT; c TEXT; k TEXT; ntab INT; i INT; x NUMERIC; acc NUMERIC; j INT; m INT; ndays INT; active BOOLEAN;
BEGIN
  PERFORM setseed(0.42);
  SELECT array_agg(kid ORDER BY kid), array_agg(pop ORDER BY kid) INTO kabs, pops FROM (VALUES ('3578',2949496), ('3573',844614), ('3571',287609), ('3577',178540), ('3574',239649), ('3510',1719287), ('3529',1144719), ('3509',2606656), ('3501',592786), ('3502',956000), ('3503',733700), ('3504',1077500), ('3505',1213000), ('3506',1626100), ('3507',2716000), ('3508',1129500), ('3511',790180), ('3512',690600), ('3513',1208400), ('3514',1683700), ('3515',2185300), ('3516',1175000), ('3517',1357300), ('3518',1075800), ('3519',743200), ('3520',679000), ('3521',889600), ('3522',1357000), ('3523',1218000), ('3524',1378200), ('3525',1330000), ('3526',1062200), ('3527',984000), ('3528',892800), ('3572',148800), ('3575',211800), ('3576',146100), ('3579',213700)) v(kid, pop);
  SELECT sum(pop) INTO totpop FROM (VALUES ('3578',2949496), ('3573',844614), ('3571',287609), ('3577',178540), ('3574',239649), ('3510',1719287), ('3529',1144719), ('3509',2606656), ('3501',592786), ('3502',956000), ('3503',733700), ('3504',1077500), ('3505',1213000), ('3506',1626100), ('3507',2716000), ('3508',1129500), ('3511',790180), ('3512',690600), ('3513',1208400), ('3514',1683700), ('3515',2185300), ('3516',1175000), ('3517',1357300), ('3518',1075800), ('3519',743200), ('3520',679000), ('3521',889600), ('3522',1357000), ('3523',1218000), ('3524',1378200), ('3525',1330000), ('3526',1062200), ('3527',984000), ('3528',892800), ('3572',148800), ('3575',211800), ('3576',146100), ('3579',213700)) v(kid, pop);
  FOR p IN 1..220 LOOP
    x := random() * totpop; acc := 0; home := kabs[1];
    FOR j IN 1..array_length(kabs,1) LOOP acc := acc + pops[j]; IF x <= acc THEN home := kabs[j]; EXIT; END IF; END LOOP;
    signed := random() < 0.15;
    ndays := 1 + floor(random() * random() * 6)::int;
    FOR d IN 0..38 LOOP
      day := DATE '2026-08-01' + d;
      active := random() < (CASE WHEN extract(isodow FROM day) >= 6 THEN 0.05 ELSE 0.10 END) * ndays / 2.0 * (0.6 + 0.4 * d / 38.0);
      IF d = 38 AND p <= 30 THEN active := true; END IF;
      CONTINUE WHEN NOT active;
      tok := encode(sha256(('demo:' || p || ':' || day)::bytea), 'hex');
      sid := md5('demo-session:' || p || ':' || day)::uuid;
      base := (day::timestamp + make_interval(hours => 6 + floor(random()*15)::int, mins => floor(random()*60)::int)) AT TIME ZONE 'Asia/Jakarta';
      t := base;
      INSERT INTO intent_event (ts, channel, event_type, detail, day_token, session_id, signed_in, consent_version, app_version)
        VALUES (t, 'web', 'session_start', jsonb_build_object('path','/dashboard','source','demo','viewport_w',1440,'viewport_h',900), tok, sid, signed, '2026-09-v1', 'demo-seed'),
               (t, 'web', 'page_view', jsonb_build_object('path','/dashboard','source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
      ntab := 2 + floor(random()*5)::int;
      FOR i IN 1..ntab LOOP
        t := t + make_interval(secs => 8 + floor(random()*40)::int);
        x := random(); acc := 0; j := 1;
        WHILE j < array_length(tabs,1) AND x > acc + tw[j] LOOP acc := acc + tw[j]; j := j + 1; END LOOP;
        INSERT INTO intent_event (ts, channel, event_type, detail, day_token, session_id, signed_in, consent_version, app_version)
          VALUES (t, 'web', 'ui_click', jsonb_build_object('tag','button','label',labels[j],'path','/dashboard','source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed'),
                 (t, 'web', 'tab_view', jsonb_build_object('tab',tabs[j],'source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
        IF random() < 0.45 THEN
          x := random(); acc := 0; c := comms[1];
          FOR m IN 1..array_length(comms,1) LOOP acc := acc + cw[m]; IF x <= acc THEN c := comms[m]; EXIT; END IF; END LOOP;
          t := t + make_interval(secs => 3 + floor(random()*10)::int);
          INSERT INTO intent_event (ts, channel, event_type, commodity, detail, day_token, session_id, signed_in, consent_version, app_version)
            VALUES (t, 'web', 'commodity_pick', c, jsonb_build_object('tab',tabs[j],'source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
        ELSE
          c := comms[1 + floor(random()*3)::int];
        END IF;
        IF tabs[j] IN ('peta','distribusi','beranda') AND random() < 0.55 THEN
          k := CASE WHEN random() < 0.6 THEN home ELSE kabs[1 + floor(random()*array_length(kabs,1))::int] END;
          t := t + make_interval(secs => 4 + floor(random()*12)::int);
          INSERT INTO intent_event (ts, channel, event_type, commodity, kabupaten_id, detail, day_token, session_id, signed_in, consent_version, app_version)
            VALUES (t, 'web', 'kabupaten_pick', c, k, jsonb_build_object('surface',tabs[j],'source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
          IF tabs[j] = 'distribusi' AND random() < 0.4 THEN
            t := t + make_interval(secs => 5);
            INSERT INTO intent_event (ts, channel, event_type, commodity, kabupaten_id, detail, day_token, session_id, signed_in, consent_version, app_version)
              VALUES (t, 'web', 'explain_view', c, k, jsonb_build_object('deficit_kab_id',k,'source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
          END IF;
        END IF;
        IF tabs[j] = 'harga' THEN
          k := CASE WHEN random() < 0.7 THEN home ELSE kabs[1 + floor(random()*array_length(kabs,1))::int] END;
          t := t + make_interval(secs => 6);
          INSERT INTO intent_event (ts, channel, event_type, commodity, kabupaten_id, detail, day_token, session_id, signed_in, consent_version, app_version)
            VALUES (t, 'web', 'forecast_view', c, k, jsonb_build_object('method','timesfm_2.0','n_points',30,'source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
          IF random() < 0.5 THEN
            INSERT INTO intent_event (ts, channel, event_type, commodity, kabupaten_id, detail, day_token, session_id, signed_in, consent_version, app_version)
              VALUES (t + interval '1 second', 'web', 'anomaly_view', c, k, jsonb_build_object('n_anomalies', 1 + floor(random()*6)::int,'source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
          END IF;
        END IF;
        IF tabs[j] = 'simulasi' AND random() < 0.7 THEN
          t := t + make_interval(secs => 20 + floor(random()*40)::int);
          INSERT INTO intent_event (ts, channel, event_type, commodity, detail, day_token, session_id, signed_in, consent_version, app_version)
            VALUES (t, 'web', 'simulate_run', c, jsonb_build_object('presets', presets[1 + floor(random()*array_length(presets,1))::int], 'bbm_pct', (floor(random()*4)*5)::int, 'n_matches', 15 + floor(random()*12)::int, 'source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
        END IF;
        IF tabs[j] IN ('laporan','distribusi') AND random() < 0.25 THEN
          t := t + make_interval(secs => 10);
          INSERT INTO intent_event (ts, channel, event_type, commodity, detail, day_token, session_id, signed_in, consent_version, app_version)
            VALUES (t, 'web', 'download', c, jsonb_build_object('kind','report_csv','source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
        END IF;
      END LOOP;
      t := t + make_interval(secs => 15 + floor(random()*90)::int);
      INSERT INTO intent_event (ts, channel, event_type, detail, day_token, session_id, signed_in, consent_version, app_version)
        VALUES (t, 'web', 'session_end', jsonb_build_object('path','/dashboard','duration_ms', (extract(epoch FROM (t - base))*1000)::int, 'source','demo'), tok, sid, signed, '2026-09-v1', 'demo-seed');
    END LOOP;
  END LOOP;
END $$;
