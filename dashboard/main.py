import argparse
import logging
import sys
from dashboard.core.app import DashboardApp

def setup_basic_logging():
    """Setup basic stdout logging before config is loaded"""
    root_logger = logging.getLogger()
    if not root_logger.handlers:  # Only add handler if none exists
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        ))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)  # Set initial level to DEBUG
        logging.debug("Basic logging initialized")

if __name__ == "__main__":
    # Setup basic logging
    setup_basic_logging()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Personal Dashboard')
    parser.add_argument('--config', 
                       help='Path to config file (default: app_directory/config/config.yaml)')
    
    args = parser.parse_args()
    config_path = args.config if args.config else "config.yaml"
    
    # Create and run app
    app = DashboardApp(config_path=config_path)
    app.run() 