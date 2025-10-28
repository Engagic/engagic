-- Auto-generated SQL fixes from verify_and_fix_all_cities.py
-- Generated: 2025-10-28 05:00:21

BEGIN TRANSACTION;

UPDATE cities SET slug='missouricityTX', updated_at=CURRENT_TIMESTAMP WHERE banana='missouricityTX'; -- Missouri City, TX
UPDATE cities SET slug='auburn', updated_at=CURRENT_TIMESTAMP WHERE banana='auburnWA'; -- Auburn, WA
UPDATE cities SET slug='cityofclovis', updated_at=CURRENT_TIMESTAMP WHERE banana='clovisCA'; -- Clovis, CA
UPDATE cities SET slug='cityofclovis', updated_at=CURRENT_TIMESTAMP WHERE banana='clovisNM'; -- Clovis, NM
UPDATE cities SET slug='concordNH', updated_at=CURRENT_TIMESTAMP WHERE banana='concordNH'; -- Concord, NH
UPDATE cities SET slug='davenport', updated_at=CURRENT_TIMESTAMP WHERE banana='davenportIA'; -- Davenport, IA
UPDATE cities SET slug='georgetown', updated_at=CURRENT_TIMESTAMP WHERE banana='georgetownTX'; -- Georgetown, TX
UPDATE cities SET slug='jonesboro', updated_at=CURRENT_TIMESTAMP WHERE banana='jonesboroAR'; -- Jonesboro, AR
UPDATE cities SET slug='kearney', updated_at=CURRENT_TIMESTAMP WHERE banana='kearneyNE'; -- Kearney, NE
UPDATE cities SET slug='miamiFL', updated_at=CURRENT_TIMESTAMP WHERE banana='miamiFL'; -- Miami, FL
UPDATE cities SET slug='miamibeachFL', updated_at=CURRENT_TIMESTAMP WHERE banana='miamibeachFL'; -- Miami Beach, FL
UPDATE cities SET slug='cityofmonroe', updated_at=CURRENT_TIMESTAMP WHERE banana='monroeLA'; -- Monroe, LA
UPDATE cities SET slug='cityofmonroe', updated_at=CURRENT_TIMESTAMP WHERE banana='monroeMI'; -- Monroe, MI
UPDATE cities SET slug='cityofnewportrichey', updated_at=CURRENT_TIMESTAMP WHERE banana='newportricheyFL'; -- New Port Richey, FL
UPDATE cities SET slug='plainfieldIL', updated_at=CURRENT_TIMESTAMP WHERE banana='plainfieldIL'; -- Plainfield, IL
UPDATE cities SET slug='salem', updated_at=CURRENT_TIMESTAMP WHERE banana='salemOR'; -- Salem, OR
UPDATE cities SET slug='salem', updated_at=CURRENT_TIMESTAMP WHERE banana='salemMA'; -- Salem, MA
UPDATE cities SET slug='tampa', updated_at=CURRENT_TIMESTAMP WHERE banana='tampaFL'; -- Tampa, FL
UPDATE cities SET slug='taylor', updated_at=CURRENT_TIMESTAMP WHERE banana='taylorMI'; -- Taylor, MI
UPDATE cities SET slug='canton', updated_at=CURRENT_TIMESTAMP WHERE banana='cantonMI'; -- Canton, MI
UPDATE cities SET slug='canton', updated_at=CURRENT_TIMESTAMP WHERE banana='cantonGA'; -- Canton, GA
UPDATE cities SET slug='cityofcleveland', updated_at=CURRENT_TIMESTAMP WHERE banana='clevelandOH'; -- Cleveland, OH
UPDATE cities SET slug='cityofcleveland', updated_at=CURRENT_TIMESTAMP WHERE banana='clevelandTN'; -- Cleveland, TN
UPDATE cities SET slug='columbus', updated_at=CURRENT_TIMESTAMP WHERE banana='columbusOH'; -- Columbus, OH
UPDATE cities SET slug='columbus', updated_at=CURRENT_TIMESTAMP WHERE banana='columbusGA'; -- Columbus, GA
UPDATE cities SET slug='columbus', updated_at=CURRENT_TIMESTAMP WHERE banana='columbusMS'; -- Columbus, MS
UPDATE cities SET slug='cityofdallas', updated_at=CURRENT_TIMESTAMP WHERE banana='dallasTX'; -- Dallas, TX
UPDATE cities SET slug='cityofdallas', updated_at=CURRENT_TIMESTAMP WHERE banana='dallasGA'; -- Dallas, GA
UPDATE cities SET slug='cityoffayetteville', updated_at=CURRENT_TIMESTAMP WHERE banana='fayettevilleGA'; -- Fayetteville, GA
UPDATE cities SET slug='gainesville', updated_at=CURRENT_TIMESTAMP WHERE banana='gainesvilleGA'; -- Gainesville, GA
UPDATE cities SET slug='hampton', updated_at=CURRENT_TIMESTAMP WHERE banana='hamptonGA'; -- Hampton, GA
UPDATE cities SET slug='jonesboro', updated_at=CURRENT_TIMESTAMP WHERE banana='jonesboroGA'; -- Jonesboro, GA
UPDATE cities SET slug='lexington', updated_at=CURRENT_TIMESTAMP WHERE banana='lexingtonKY'; -- Lexington, KY
UPDATE cities SET slug='lexington', updated_at=CURRENT_TIMESTAMP WHERE banana='lexingtonSC'; -- Lexington, SC
UPDATE cities SET slug='lexington', updated_at=CURRENT_TIMESTAMP WHERE banana='lexingtonNC'; -- Lexington, NC
UPDATE cities SET slug='madison', updated_at=CURRENT_TIMESTAMP WHERE banana='madisonWI'; -- Madison, WI
UPDATE cities SET slug='newark', updated_at=CURRENT_TIMESTAMP WHERE banana='newarkDE'; -- Newark, DE
UPDATE cities SET slug='salem', updated_at=CURRENT_TIMESTAMP WHERE banana='salemVA'; -- Salem, VA
UPDATE cities SET slug='wilmington', updated_at=CURRENT_TIMESTAMP WHERE banana='wilmingtonDE'; -- Wilmington, DE
UPDATE cities SET slug='ankeny', updated_at=CURRENT_TIMESTAMP WHERE banana='ankenyIA'; -- Ankeny, IA
UPDATE cities SET slug='cityofarlingtonheights', updated_at=CURRENT_TIMESTAMP WHERE banana='arlingtonheightsIL'; -- Arlington Heights, IL
UPDATE cities SET slug='cityofdaytonabeach', updated_at=CURRENT_TIMESTAMP WHERE banana='daytonabeachFL'; -- Daytona Beach, FL
UPDATE cities SET slug='lakeforest', updated_at=CURRENT_TIMESTAMP WHERE banana='lakeforestCA'; -- Lake Forest, CA
UPDATE cities SET slug='midland', updated_at=CURRENT_TIMESTAMP WHERE banana='midlandTX'; -- Midland, TX
UPDATE cities SET slug='prescottvalley', updated_at=CURRENT_TIMESTAMP WHERE banana='prescottvalleyAZ'; -- Prescott Valley, AZ
UPDATE cities SET slug='sanantonio', updated_at=CURRENT_TIMESTAMP WHERE banana='sanantonioTX'; -- San Antonio, TX
UPDATE cities SET slug='cityoftemple', updated_at=CURRENT_TIMESTAMP WHERE banana='templeTX'; -- Temple, TX
UPDATE cities SET slug='cityofwestminster', updated_at=CURRENT_TIMESTAMP WHERE banana='westminsterMD'; -- Westminster, MD

COMMIT;
