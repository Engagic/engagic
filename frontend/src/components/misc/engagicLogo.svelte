<script lang="ts">
    let animated = $state(false);
    
    const startAnimation = () => {
        animated = true;
        setTimeout(() => animated = false, 1000);
    };
</script>

<div id="engagic-logo" onclick={startAnimation}>
    <div class="logo-container" class:animated>
        <div class="civic-icon">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <!-- Government building icon with modern civic feel -->
                <rect x="8" y="36" width="32" height="8" rx="2" fill="url(#civic-gradient)"/>
                <rect x="12" y="20" width="4" height="16" fill="url(#civic-gradient)"/>
                <rect x="16" y="16" width="4" height="20" fill="url(#civic-gradient)"/>
                <rect x="20" y="12" width="8" height="24" rx="1" fill="url(#civic-gradient)"/>
                <rect x="28" y="16" width="4" height="20" fill="url(#civic-gradient)"/>
                <rect x="32" y="20" width="4" height="16" fill="url(#civic-gradient)"/>
                
                <!-- Stars representing civic engagement -->
                <circle cx="14" cy="8" r="2" fill="var(--civic-gold)" class="star star-1"/>
                <circle cx="24" cy="4" r="2.5" fill="var(--civic-gold)" class="star star-2"/>
                <circle cx="34" cy="8" r="2" fill="var(--civic-gold)" class="star star-3"/>
                
                <defs>
                    <linearGradient id="civic-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" style="stop-color:var(--civic-blue);stop-opacity:1" />
                        <stop offset="100%" style="stop-color:var(--civic-blue-light);stop-opacity:1" />
                    </linearGradient>
                </defs>
            </svg>
        </div>
        <div class="logo-text">
            <h1>engagic</h1>
            <p>democracy made accessible</p>
        </div>
    </div>
</div>

<style>
    #engagic-logo {
        cursor: pointer;
        user-select: none;
        transition: transform 0.2s ease;
    }
    
    #engagic-logo:hover {
        transform: scale(1.02);
    }
    
    .logo-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 16px;
        padding: 20px;
    }
    
    .civic-icon {
        position: relative;
        transition: all 0.3s ease;
    }
    
    .logo-container.animated .civic-icon {
        animation: logoFloat 1s ease-in-out;
    }
    
    .star {
        transition: all 0.3s ease;
        transform-origin: center;
    }
    
    .logo-container.animated .star-1 {
        animation: starTwinkle 1s ease-in-out 0.1s;
    }
    
    .logo-container.animated .star-2 {
        animation: starTwinkle 1s ease-in-out 0.2s;
    }
    
    .logo-container.animated .star-3 {
        animation: starTwinkle 1s ease-in-out 0.3s;
    }
    
    .logo-text {
        text-align: center;
    }
    
    .logo-text h1 {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0;
        background: var(--civic-gradient);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: -0.02em;
    }
    
    .logo-text p {
        margin: 4px 0 0 0;
        font-size: 0.95rem;
        color: var(--gray);
        font-weight: 500;
        letter-spacing: 0.02em;
    }
    
    @keyframes logoFloat {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-8px); }
    }
    
    @keyframes starTwinkle {
        0%, 100% { transform: scale(1) rotate(0deg); opacity: 1; }
        25% { transform: scale(1.3) rotate(45deg); opacity: 0.8; }
        50% { transform: scale(1.1) rotate(90deg); opacity: 1; }
        75% { transform: scale(1.2) rotate(135deg); opacity: 0.9; }
    }
    
    @media screen and (max-width: 640px) {
        .logo-text h1 {
            font-size: 2rem;
        }
        
        .logo-text p {
            font-size: 0.875rem;
        }
        
        .civic-icon svg {
            width: 40px;
            height: 40px;
        }
    }
</style>