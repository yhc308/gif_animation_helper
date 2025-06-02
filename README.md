<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gif_Animation_Sampler 프로젝트 업데이트</title>
    <style>
        body {
            font-family: 'Malgun Gothic', '맑은 고딕', sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f4f4f4;
            color: #333;
        }
        .container {
            max-width: 800px;
            margin: auto;
            background: #fff;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 0 15px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            text-align: center;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            font-size: 1.2em;
            margin-top: 0;
        }
        .version-info {
            background-color: #eaf2f8;
            border-left: 5px solid #3498db;
            padding: 10px 15px;
            margin: 15px 0;
            font-style: italic;
        }
        h3 {
            color: #16a085;
            border-bottom: 1px solid #ddd;
            padding-bottom: 5px;
            margin-top: 30px;
        }
        ul {
            list-style-type: none;
            padding-left: 0;
        }
        li {
            background-color: #ecf0f1;
            margin-bottom: 10px;
            padding: 10px 15px;
            border-radius: 4px;
        }
        li strong {
            color: #c0392b; /* 강조 텍스트 색상 */
        }
        ul ul {
            margin-top: 8px;
            padding-left: 20px;
        }
        ul ul li {
            background-color: #f9f9f9;
            font-size: 0.95em;
        }
        .task-description {
            font-size: 0.9em;
            color: #555;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Gif_Animation_Sampler</h1>
        <h2>GIF 애니메이션 샘플러 / 딜레이 출력기 및 애니메이션 스플리터 통합 개발버전</h2>

        <p class="version-info">Gif_Animation_Sampler_v0500.py _프리뷰 영역 작업 완료</p>

        <h3>향후 계획</h3>
        <ul>
            <li>
                버튼 시각효과 추가 및 동기화
                <ul>
                    <li class="task-description">마우스 오버시 광도 0.3 짙게 조절</li>
                </ul>
            </li>
            <li>
                프레임 설명 미리보기 영역
                <ul>
                    <li class="task-description">간격 조정</li>
                    <li class="task-description">드래그 복사</li>
                    <li class="task-description">클립보드 복사버튼 구현</li>
                </ul>
            </li>
            <li>
                <strong>(중요)</strong> Export 파일 개선
                <ul>
                    <li class="task-description">샘플용 GIF 분할 출력시 팔레트 망가짐, 투명 인덱스 망가짐.</li>
                    <li class="task-description">Pillow 에서 모든 프레임에 수동 명령을 내려도, 분리된 샘플 애니메이션들의 첫번째 프레임만 완전하게 출력되는 문제가 있음.</li>
                    <li class="task-description">이미지 뷰어상에서는 문제가 없으나, 상세 속성을 보면 첫 프레임 제외 투명인덱스와 팔레트 인덱스, 즉 256개의 인덱스가 최적화 되어버림.</li>
                    <li class="task-description">현재로써는 append 하는 과정에 자동 최적화 되는 것으로 추측됨. 자동 최적화 되지 않도록 추출하는 법을 찾는 중.</li>
                </ul>
            </li>
        </ul>
    </div>
</body>
</html>
